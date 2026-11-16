from pathlib import Path
import json
import shutil

import folder_paths
import numpy as np
from PIL import Image
from comfy_api.latest import io, ui, InputImpl, Types

from .bridge import PROFILES, export_job, read_config


def config():
    return read_config(folder_paths.get_output_directory(), folder_paths.get_temp_directory(), folder_paths.get_input_directory())


def result(rows, video=False):
    saved = [ui.SavedResult(r['filename'], r['subfolder'], io.FolderType.output) for r in rows]
    preview = ui.PreviewVideo(saved) if video else ui.SavedImages(saved)
    return io.NodeOutput(json.dumps(rows), ui=preview)


def common_inputs():
    return [io.String.Input('filename_prefix', default='ariadne'),
            io.String.Input('created_at_utc', default='', tooltip='Final rendition creation time in ISO8601 UTC; blank records materialization at this export.')]


class ExportNode(io.ComfyNode):
    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return float('nan')  # Every queued export owns a fresh file and receipt.


class AriadneExportImages(ExportNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='AriadneExportImages', display_name='Export Images with Ariadne', category='Ariadne Mark',
            description='Save newly generated final images with invisible watermark, signed C2PA and an SDK receipt. Uses your configured SDK kit; no unmarked fallback.',
            search_aliases=['watermark','C2PA','AI labeling','provenance'], is_output_node=True,
            inputs=[io.Image.Input('images'), *common_inputs()], outputs=[io.String.Output('files_json')])

    @classmethod
    def execute(cls, images, filename_prefix='ariadne', created_at_utc=''):
        if len(images.shape)!=4 or images.shape[-1] not in {3,4} or not 1<=images.shape[0]<=1000:
            raise ValueError('Expected a batch of 1–1000 RGB/RGBA images')
        if not all(256<=n<=4096 for n in images.shape[1:3]):
            raise ValueError('SDK image dimensions must be 256–4096 pixels per side')
        with export_job(config(), folder_paths.get_output_directory(), prefix=filename_prefix, created_at=created_at_utc) as job:
            for index, tensor in enumerate(images):
                pixels=np.clip(tensor.detach().cpu().numpy()*255,0,255).astype(np.uint8)
                path=job.inputs/f'image_{index:04}.png'
                Image.fromarray(pixels).save(path)
                job.add(path)
            rows=job.run()
        return result(rows)


class AriadneExportVideo(ExportNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='AriadneExportVideo', display_name='Export Video with Ariadne', category='Ariadne Mark',
            description='Export freshly generated SDR frames from Create Video (codec none) through the SDK visual watermark. All three video profiles are available.',
            search_aliases=['video watermark','C2PA video','AI labeling'], is_output_node=True,
            inputs=[io.Video.Input('video'), *common_inputs(), io.Combo.Input('video_profile', options=list(PROFILES), default='economy_5s'),
                    io.Combo.Input('audio_kind', options=['none','original'], default='none', tooltip='Original is non-synthetic audio. Synthetic audio is outside this SDK workflow.')],
            outputs=[io.String.Output('files_json')])

    @classmethod
    def execute(cls, video, filename_prefix='ariadne', created_at_utc='', video_profile='economy_5s', audio_kind='none'):
        if not isinstance(video, InputImpl.VideoFromComponents):
            raise ValueError('Connect freshly generated frames through Create Video with codec none. Use Mark Saved File for an existing final MP4.')
        width,height=video.get_dimensions()
        if any(n<256 or n>1920 or n%2 for n in [width,height]) or video.get_duration()>300 or video.get_frame_count()>18000:
            raise ValueError('SDK video requires even dimensions 256–1920 and at most 5 minutes /18000 frames')
        if video.get_bit_depth()!=8 or video.get_color_space()!='sRGB':
            raise ValueError('SDK video export requires 8-bit SDR; prepare the final SDR rendition before this node')
        with export_job(config(), folder_paths.get_output_directory(), prefix=filename_prefix, created_at=created_at_utc,
                        video_profile=video_profile, audio_kind=audio_kind) as job:
            path=job.inputs/'video.mp4'
            video.save_to(str(path), format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264, metadata=None)
            job.add(path)
            rows=job.run()
        return result(rows,video=True)


class AriadneMarkSavedFile(ExportNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='AriadneMarkSavedFile', display_name='Mark Saved File with Ariadne', category='Ariadne Mark',
            description='Pass an existing final PNG/JPEG/MP4 unchanged to the SDK. Input must be inside Comfy input/output. Existing Content Credentials retain the SDK upstream-history checks.',
            is_output_node=True, inputs=[io.String.Input('file_path', default=''),*common_inputs(),
                io.Combo.Input('video_profile', options=list(PROFILES), default='economy_5s'),
                io.Combo.Input('audio_kind', options=['none','original'], default='none')], outputs=[io.String.Output('files_json')])

    @classmethod
    def execute(cls,file_path,filename_prefix='ariadne',created_at_utc='',video_profile='economy_5s',audio_kind='none'):
        path=Path(file_path)
        if not path.is_absolute():path=Path(folder_paths.get_input_directory())/path
        path=path.resolve()
        roots=[Path(folder_paths.get_input_directory()).resolve(),Path(folder_paths.get_output_directory()).resolve()]
        if not path.is_file() or not any(path.is_relative_to(p) for p in roots) or path.suffix.lower() not in {'.png','.jpg','.jpeg','.mp4'}:
            raise ValueError('Choose a final PNG/JPEG/MP4 inside Comfy input or output')
        with export_job(config(), folder_paths.get_output_directory(), prefix=filename_prefix,created_at=created_at_utc,
                        video_profile=video_profile,audio_kind=audio_kind) as job:
            source=job.inputs/('media'+path.suffix.lower())
            shutil.copyfile(path,source)
            job.add(source)
            rows=job.run()
        return result(rows,video=path.suffix.lower()=='.mp4')
