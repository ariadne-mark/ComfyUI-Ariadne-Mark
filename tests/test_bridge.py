import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ariadne_bridge_test',ROOT/'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

FAKE = '''import json,sys,os,hashlib,subprocess,time
from pathlib import Path
root=Path(sys.argv[-2]);batch=json.loads(Path(sys.argv[-1]).read_text())
mode=os.environ.get('ARIADNE_TEST_MODE','ok')
if mode=='timeout':
 child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])
 (root/'child-pid').write_text(str(child.pid));time.sleep(90)
for i,row in enumerate(batch['jobs']):
 source=root/'inputs'/row['source'];dest=root/'outputs'/row['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
 data=source.read_bytes()+b'-marked';dest.write_bytes(data)
 receipt={'sdk_version':'0.7.3a4','registry_recorded':True,'sha256':hashlib.sha256(data).hexdigest(),'token':'014d000000000001'}
 if mode=='bad-receipt':receipt['sha256']='0'*64
 dest.with_name(dest.name+'.receipt.json').write_text(json.dumps(receipt))
 if mode=='partial-failure':sys.exit(2)
'''


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.kit=self.root/'private-kit';(self.kit/'config').mkdir(parents=True)
        (self.kit/'config/kit.json').write_text('{}')
        self.output=self.root/'comfy-output';self.output.mkdir()
        self.input=self.root/'comfy-input';self.input.mkdir()
        self.scratch=self.root/'comfy-temp';self.scratch.mkdir()
        self.worker=self.root/'fake-sdk'
        self.worker.write_text('#!'+sys.executable+'\n'+FAKE);self.worker.chmod(0o755)
        self.config={'schema_version':1,'kit_directory':str(self.kit),'runner':{'kind':'cli','command':[str(self.worker)]},'timeout_seconds':10}
        self.config_file=self.root/'adapter.local.json';self.config_file.write_text(json.dumps(self.config))
        self.env=patch.dict(os.environ,{'ARIADNE_COMFY_CONFIG':str(self.config_file)},clear=False);self.env.start()

    def tearDown(self):
        self.env.stop();self.temp.cleanup()

    def load(self):return bridge.read_config(self.output,self.scratch,self.input)

    def test_missing_config_fails(self):
        with patch.dict(os.environ,{'ARIADNE_COMFY_CONFIG':''}):
            with self.assertRaisesRegex(ValueError,'ARIADNE_COMFY_CONFIG'):self.load()

    def test_private_kit_cannot_live_in_served_output(self):
        self.config['kit_directory']=str(self.output)
        (self.output/'config').mkdir();(self.output/'config/kit.json').write_text('{}')
        self.config_file.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError,'separate'):self.load()

    def test_duplicate_config_fields_rejected(self):
        self.config_file.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.load()

    def test_docker_requires_immutable_image(self):
        self.config['runner']={'kind':'docker','command':['docker'],'image':'latest','network':'none'}
        self.config_file.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError,'immutable'):self.load()

    def test_prefix_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'prefix'):
            bridge.ExportJob(self.load(),self.output,'../escape','')

    def test_successful_batch_publishes_matching_bytes_and_receipts(self):
        with bridge.export_job(self.load(),self.output,prefix='Test',created_at='') as job:
            for n in ['a.png','b.png']:
                p=job.inputs/n;p.write_bytes(n.encode());job.add(p)
            rows=job.run();inputs=job.inputs;outputs=job.outputs
        self.assertFalse(inputs.exists());self.assertFalse(outputs.exists());self.assertEqual(2,len(rows))
        for r in rows:
            final=self.output/r['subfolder']/r['filename']
            self.assertEqual(r['sha256'],bridge.digest(final))
            self.assertTrue(final.with_name(final.name+'.receipt.json').is_file())
        self.assertTrue((self.kit/'.comfy-jobs'/job.id/'stdout.log').is_file())

    def test_partial_sdk_failure_publishes_no_batch(self):
        with patch.dict(os.environ,{'ARIADNE_TEST_MODE':'partial-failure'}):
            with bridge.export_job(self.load(),self.output,prefix='fail',created_at='') as job:
                p=job.inputs/'a.png';p.write_bytes(b'original');job.add(p)
                with self.assertRaisesRegex(RuntimeError,'no Comfy output'):job.run()
        self.assertEqual([],list(self.output.iterdir()))
        self.assertTrue((job.outputs/'a.png').is_file())

    def test_changed_receipt_publishes_nothing(self):
        with patch.dict(os.environ,{'ARIADNE_TEST_MODE':'bad-receipt'}):
            with bridge.export_job(self.load(),self.output,prefix='fail',created_at='') as job:
                p=job.inputs/'a.png';p.write_bytes(b'original');job.add(p)
                with self.assertRaisesRegex(RuntimeError,'mismatch'):job.run()
        self.assertEqual([],list(self.output.iterdir()))

    def test_timeout_terminates_worker_process_group(self):
        config=self.load();config['timeout_seconds']=0.4
        with patch.dict(os.environ,{'ARIADNE_TEST_MODE':'timeout'}):
            with bridge.export_job(config,self.output,prefix='timeout',created_at='') as job:
                p=job.inputs/'a.png';p.write_bytes(b'original');job.add(p)
                with self.assertRaises(subprocess.TimeoutExpired):job.run()
        self.assertEqual([],list(self.output.iterdir()))
        pid=int((self.kit/'child-pid').read_text());proc=Path('/proc')/str(pid)/'stat'
        for _ in range(20):
            if not proc.exists() or proc.read_text().split()[2]=='Z':break
            time.sleep(0.05)
        else:self.fail('Child process survived SDK timeout')

    def test_output_symlink_cannot_redirect_publication(self):
        outside=self.root/'outside';outside.mkdir();(self.output/'ariadne').symlink_to(outside,target_is_directory=True)
        with bridge.export_job(self.load(),self.output,prefix='blocked',created_at='') as job:
            p=job.inputs/'a.png';p.write_bytes(b'original');job.add(p)
            with self.assertRaisesRegex(ValueError,'escapes'):job.run()
        self.assertEqual([],list(outside.iterdir()))


if __name__=='__main__':unittest.main()
