import importlib
import sys

from .nodes.registry import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, WEB_DIRECTORY
from .v3_extension import comfy_entrypoint


_LEGACY_MODULE_ALIASES = {
    "preview_collage": ".nodes.preview_nodes",
    "xcine": ".nodes.xcine",
    "xcolor": ".nodes.xcolor",
    "xconcepts": ".nodes.xconcepts",
    "xlut": ".nodes.xlut",
    "xmask": ".nodes.mask_nodes",
    "xmedia_batch1_nodes": ".nodes.media_batch_video_nodes",
    "xmedia_batch2_nodes": ".nodes.media_batch_transform_nodes",
    "xmedia_batch3_nodes": ".nodes.media_batch_watermark_audio_nodes",
    "xmedia_batch4_nodes": ".nodes.media_batch_analysis_nodes",
    "xmedia_batch5_nodes": ".nodes.media_batch_cinematic_nodes",
    "xmedia_batch6_nodes": ".nodes.media_batch_audio_delivery_nodes",
    "xmedia_extra_nodes": ".nodes.media_extra_nodes",
    "xmedia_nodes": ".nodes.media_io_nodes",
    "xphoto": ".nodes.xphoto",
    "xplay": ".nodes.xplay",
    "xpresave": ".nodes.presave_image_nodes",
    "xpresave_media": ".nodes.presave_media_nodes",
    "xprocess": ".nodes.xprocess",
    "xresize": ".nodes.xresize",
    "xshader": ".nodes.xshader",
    "xshared": ".lib.image_shared",
    "xutility_photo": ".nodes.xutility_photo",
}

for alias, target in _LEGACY_MODULE_ALIASES.items():
    sys.modules.setdefault(f"{__name__}.{alias}", importlib.import_module(target, __name__))

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY", "comfy_entrypoint"]
