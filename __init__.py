from comfy_api.latest import ComfyExtension
from .nodes import AriadneExportImages, AriadneExportVideo, AriadneMarkSavedFile


class AriadneExtension(ComfyExtension):
    async def get_node_list(self):
        return [AriadneExportImages, AriadneExportVideo, AriadneMarkSavedFile]


async def comfy_entrypoint():
    return AriadneExtension()
