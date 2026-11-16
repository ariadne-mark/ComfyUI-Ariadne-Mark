"""Run the existing SDK kit in an isolated operator-configured environment."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import uuid

from filelock import FileLock, Timeout

SDK_VERSION = '0.7.3a4'
PROFILES = ('economy_5s', 'economy_2s', 'resilient')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate configuration field: ' + key)
        result[key] = value
    return result


def read_config(output_root, temp_root, input_root):
    name = os.environ.get('ARIADNE_COMFY_CONFIG', '')
    if not name:
        raise ValueError('Set ARIADNE_COMFY_CONFIG to your private adapter JSON; see the adapter README.')
    file = Path(name).expanduser().resolve()
    if not file.is_file() or file.stat().st_size > 65536:
        raise ValueError('Adapter config must be a JSON file under 64 KiB')
    config = json.loads(file.read_text(), object_pairs_hook=_unique_object)
    if set(config) != {'schema_version', 'kit_directory', 'runner', 'timeout_seconds'} or config['schema_version'] != 1:
        raise ValueError('Unexpected adapter configuration fields')
    if type(config['timeout_seconds']) is not int or not 10 <= config['timeout_seconds'] <= 3600:
        raise ValueError('Use timeout_seconds between 10 and 3600')
    kit = Path(config['kit_directory']).expanduser()
    if not kit.is_absolute():
        raise ValueError('kit_directory must be absolute')
    kit = kit.resolve()
    if not (kit/'config/kit.json').is_file():
        raise ValueError('Initialize the SDK deployment kit first')
    # Comfy serves input/output/temp files. Credentials must remain outside them.
    for public in [output_root, temp_root, input_root]:
        public = Path(public).resolve()
        if kit.is_relative_to(public) or public.is_relative_to(kit) or file.is_relative_to(public):
            raise ValueError('Keep the kit and adapter config separate from Comfy input/output/temp directories')
    runner = config['runner']
    if not isinstance(runner, dict) or runner.get('kind') not in {'docker', 'cli'}:
        raise ValueError('runner.kind must be docker or cli')
    expected = {'kind', 'command', 'image', 'network'} if runner['kind'] == 'docker' else {'kind', 'command'}
    if set(runner) != expected:
        raise ValueError('Unexpected runner fields')
    command = runner['command']
    if (not isinstance(command, list) or not 1 <= len(command) <= 5
            or any(not isinstance(v, str) or not v or '\x00' in v for v in command)):
        raise ValueError('Use a non-empty command array in the private operator config')
    if runner['kind'] == 'docker':
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', runner['image']):
            raise ValueError('Pin the local Docker image by its immutable sha256 ID')
        if runner['network'] not in {'none', 'bridge'}:
            raise ValueError('Use none for offline development, or explicitly provision bridge egress for production TSA')
    elif len(command) != 1 or not Path(command[0]).is_absolute():
        raise ValueError('CLI runner needs the absolute ariadne executable in its isolated SDK environment')
    config['kit_directory'] = kit
    return config


def creation_time(value):
    if not value.strip():
        # The node materializes a new final rendition now; an earlier generation
        # time can be supplied explicitly instead of being inferred from a graph.
        return datetime.now(timezone.utc).isoformat()
    created = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if created.utcoffset() is None:
        raise ValueError('created_at_utc must include a timezone')
    return created.isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


class ExportJob:
    def __init__(self, config, output_root, prefix, created_at, video_profile='economy_5s', audio_kind='none'):
        if not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', prefix):
            raise ValueError('Use a filename prefix of 1–64 letters, numbers, underscores or hyphens')
        if video_profile not in PROFILES or audio_kind not in {'none', 'original'}:
            raise ValueError('Unknown video profile or audio declaration')
        self.config = config
        self.kit = config['kit_directory']
        self.output_root = Path(output_root).resolve()
        self.prefix = prefix
        self.created_at = creation_time(created_at)
        self.profile = video_profile
        self.audio = audio_kind
        self.id = uuid.uuid4().hex
        self.relative = Path('comfy')/self.id
        self.inputs = self.kit/'inputs'/self.relative
        self.outputs = self.kit/'outputs'/self.relative
        self.private = self.kit/'.comfy-jobs'/self.id
        self.inputs.mkdir(parents=True, mode=0o700)
        self.private.mkdir(parents=True, mode=0o700)
        self.jobs = []

    def add(self, source):
        source = Path(source).resolve()
        if source.parent != self.inputs.resolve() or source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.mp4'}:
            raise ValueError('Only the final files staged by this job may be exported')
        row = {'source': str(self.relative/source.name), 'destination': str(self.relative/source.name), 'created_at': self.created_at}
        if source.suffix.lower() == '.mp4':
            row.update(video_profile=self.profile, audio_kind=self.audio)
        self.jobs.append(row)

    def command(self):
        runner = self.config['runner']
        if runner['kind'] == 'cli':
            return runner['command'] + ['kit', 'export', str(self.kit), str(self.private/'batch.json')]
        user = str(os.getuid())+':'+str(os.getgid()) if hasattr(os, 'getuid') else '10001:10001'
        return runner['command'] + ['run', '--rm', '--pull', 'never', '--platform', 'linux/amd64',
            '--name', 'ariadne-comfy-'+self.id, '--network', runner['network'], '--cpus', '2', '--memory', '4g',
            '--user', user, '--read-only', '--tmpfs', '/tmp:rw,nosuid,size=512m',
            '-e', 'HOME=/tmp', '-e', 'CUDA_VISIBLE_DEVICES=', '-e', 'ARIADNE_KIT_EXPECTED_SDK='+SDK_VERSION,
            '-v', str(self.kit)+':/kit', runner['image'], 'kit', 'export', '/kit', '/kit/.comfy-jobs/'+self.id+'/batch.json']

    def _stop(self, process):
        try:
            if self.config['runner']['kind'] == 'docker':
                subprocess.run(self.config['runner']['command']+['rm', '-f', 'ariadne-comfy-'+self.id],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
        finally:
            if process.poll() is None:
                try:
                    if os.name == 'posix': os.killpg(process.pid, signal.SIGTERM)
                    else: process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
                    else: process.kill()
                    process.wait(timeout=5)

    def run(self):
        if not 1 <= len(self.jobs) <= 1000:
            raise ValueError('SDK batches support 1–1000 files')
        (self.private/'batch.json').write_text(json.dumps({'schema_version': 1, 'jobs': self.jobs})+'\n')
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env.pop('VIRTUAL_ENV', None)
        env.update(ARIADNE_KIT_EXPECTED_SDK=SDK_VERSION, CUDA_VISIBLE_DEVICES='', PYTHONNOUSERSITE='1')
        lock = FileLock(str(self.kit/'.comfy-export.lock'))
        try:
            with lock.acquire(timeout=5), (self.private/'stdout.log').open('w') as out, (self.private/'stderr.log').open('w') as err:
                process = subprocess.Popen(self.command(), stdout=out, stderr=err, env=env, start_new_session=(os.name == 'posix'))
                try:
                    code = process.wait(timeout=self.config['timeout_seconds'])
                except BaseException:
                    self._stop(process)
                    raise
                if code != 0:
                    raise RuntimeError('Ariadne export failed; no Comfy output published. Inspect private kit job '+self.id)
        except Timeout as exc:
            raise RuntimeError('Another Ariadne export is using this kit; retry when it finishes') from exc
        results = self.publish()
        shutil.rmtree(self.outputs)
        return results

    def publish(self):
        prepared = []
        for row in self.jobs:
            name = Path(row['destination']).name
            source = self.outputs/name
            receipt_file = source.with_name(name+'.receipt.json')
            receipt = json.loads(receipt_file.read_text())
            if (receipt.get('sdk_version') != SDK_VERSION or not receipt.get('registry_recorded')
                    or not re.fullmatch(r'[0-9a-f]{16}', receipt.get('token', ''))
                    or receipt.get('sha256') != digest(source)):
                raise RuntimeError('SDK receipt/file mismatch; no Comfy output published. Job '+self.id)
            prepared.append((source, receipt_file, receipt))
        parent = self.output_root/'ariadne'
        parent.mkdir(parents=True, exist_ok=True)
        if not parent.resolve().is_relative_to(self.output_root):
            raise ValueError('Comfy output path escapes its configured directory')
        folder = self.prefix+'_'+self.id
        final = parent/folder
        staging = Path(tempfile.mkdtemp(prefix='.publishing-', dir=parent))
        results = []
        try:
            for source, receipt_file, receipt in prepared:
                target = staging/source.name
                shutil.copyfile(source, target)
                if digest(target) != receipt['sha256']:
                    raise RuntimeError('Output changed during copy')
                shutil.copyfile(receipt_file, staging/receipt_file.name)
                results.append({'filename':source.name, 'subfolder':'ariadne/'+folder, 'type':'output',
                                'sha256':receipt['sha256'], 'token':receipt['token'], 'receipt':receipt_file.name,
                                'sdk_version':SDK_VERSION, 'video_profile':receipt.get('video',{}).get('profile')})
            (staging/'export.json').write_text(json.dumps({'schema_version':1,'files':results},indent=2)+'\n')
            os.replace(staging, final)
        finally:
            if staging.exists():shutil.rmtree(staging)
        return results


@contextmanager
def export_job(config, output_root, **options):
    job = ExportJob(config, output_root, **options)
    try:
        yield job
    finally:
        # Only generated staging inputs are transient. Logs and SDK outputs stay
        # in the private kit for an operator's explicit retention policy.
        shutil.rmtree(job.inputs)
