"""
Optional V3 schema companion nodes for MKRShift.

These focus on the newer addon/network bridge features where the V3 API gives us
cleaner schema definitions without forcing a risky full-pack migration.
"""

from __future__ import annotations

from typing import Any

try:
    from comfy_api.v0_0_2 import ComfyExtension, io
except Exception:  # pragma: no cover
    ComfyExtension = None
    io = None


if io is not None:
    from .nodes.network_addon_nodes import (
        MKRNDIStreamPlan as _V1NDI,
        MKROSCMessagePlan as _V1OSC,
        MKRSpoutSenderPlan as _V1Spout,
        MKRWebSocketBridgePlan as _V1WebSocket,
    )
    from .nodes.touchdesigner_bridge_nodes import MKRTouchDesignerFramePlan as _V1TD
    from .nodes.tixl_bridge_nodes import MKRTiXLFramePlan as _V1TiXL

    class _BaseV3(io.ComfyNode):
        CATEGORY = "MKRShift Nodes/Addons"

        @classmethod
        def fingerprint_inputs(cls, **kwargs):
            return repr(sorted(kwargs.items()))


    class MKRV3OSCMessagePlan(_BaseV3):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="MKRV3OSCMessagePlan",
                display_name="OSC Message Plan (V3)",
                category="MKRShift Nodes/Addons/Network",
                description="V3 schema companion for building OSC transport packets.",
                search_aliases=["osc", "network", "transport", "v3"],
                inputs=[
                    io.String.Input("address", default="/mkrshift/frame"),
                    io.String.Input("host", default="127.0.0.1"),
                    io.Int.Input("port", default=7000, min=1, max=65535),
                    io.String.Input("payload_json", default="{}", multiline=True),
                ],
                outputs=[
                    io.String.Output("osc_plan_json"),
                    io.String.Output("manifest_line"),
                    io.String.Output("summary_json"),
                ],
            )

        @classmethod
        def execute(cls, address: str, host: str, port: int, payload_json: str) -> io.NodeOutput:
            return io.NodeOutput(*_V1OSC().build(address, host, port, payload_json))


    class MKRV3NDIStreamPlan(_BaseV3):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="MKRV3NDIStreamPlan",
                display_name="NDI Stream Plan (V3)",
                category="MKRShift Nodes/Addons/Network",
                description="V3 schema companion for building NDI stream plans.",
                search_aliases=["ndi", "network", "transport", "v3"],
                inputs=[
                    io.String.Input("stream_name", default="MKRShift NDI"),
                    io.String.Input("asset_path", default=""),
                    io.Combo.Input("source_kind", options=["image", "image_sequence", "video", "texture"], default="video"),
                    io.Combo.Input("alpha_mode", options=["ignore", "premultiplied", "straight"], default="ignore"),
                ],
                outputs=[
                    io.String.Output("ndi_plan_json"),
                    io.String.Output("manifest_line"),
                    io.String.Output("summary_json"),
                ],
            )

        @classmethod
        def execute(cls, stream_name: str, asset_path: str, source_kind: str, alpha_mode: str) -> io.NodeOutput:
            return io.NodeOutput(*_V1NDI().build(stream_name, asset_path, source_kind, alpha_mode))


    class MKRV3SpoutSenderPlan(_BaseV3):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="MKRV3SpoutSenderPlan",
                display_name="Spout Sender Plan (V3)",
                category="MKRShift Nodes/Addons/Network",
                description="V3 schema companion for building Spout sender plans.",
                search_aliases=["spout", "network", "transport", "v3"],
                inputs=[
                    io.String.Input("sender_name", default="MKRShift Spout"),
                    io.String.Input("asset_path", default=""),
                    io.Combo.Input("source_kind", options=["image", "image_sequence", "video", "texture"], default="texture"),
                ],
                outputs=[
                    io.String.Output("spout_plan_json"),
                    io.String.Output("manifest_line"),
                    io.String.Output("summary_json"),
                ],
            )

        @classmethod
        def execute(cls, sender_name: str, asset_path: str, source_kind: str) -> io.NodeOutput:
            return io.NodeOutput(*_V1Spout().build(sender_name, asset_path, source_kind))


    class MKRV3WebSocketBridgePlan(_BaseV3):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="MKRV3WebSocketBridgePlan",
                display_name="WebSocket Bridge Plan (V3)",
                category="MKRShift Nodes/Addons/Network",
                description="V3 schema companion for building WebSocket bridge packets.",
                search_aliases=["websocket", "ws", "network", "transport", "v3"],
                inputs=[
                    io.String.Input("url", default="ws://127.0.0.1:8188/mkrshift"),
                    io.String.Input("channel", default="frame"),
                    io.String.Input("payload_json", default="{}", multiline=True),
                ],
                outputs=[
                    io.String.Output("websocket_plan_json"),
                    io.String.Output("manifest_line"),
                    io.String.Output("summary_json"),
                ],
            )

        @classmethod
        def execute(cls, url: str, channel: str, payload_json: str) -> io.NodeOutput:
            return io.NodeOutput(*_V1WebSocket().build(url, channel, payload_json))


    class MKRV3TouchDesignerFramePlan(_BaseV3):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="MKRV3TouchDesignerFramePlan",
                display_name="TouchDesigner Frame Plan (V3)",
                category="MKRShift Nodes/Addons/TouchDesigner",
                description="V3 schema companion for TouchDesigner frame return plans.",
                search_aliases=["touchdesigner", "td", "tox", "v3"],
                inputs=[
                    io.String.Input("asset_path", default=""),
                    io.Combo.Input("transport", options=["file", "spout", "ndi", "shared_memory", "websocket"], default="file"),
                    io.String.Input("top_name", default="mkrshiftTOP"),
                    io.String.Input("operator_path", default="/project1/mkrshift_bridge1"),
                    io.Combo.Input("asset_kind", options=["image", "image_sequence", "video", "texture"], default="image"),
                    io.Combo.Input("colorspace", options=["sRGB", "Linear", "Non-Color"], default="sRGB"),
                    io.String.Input("metadata_json", default="", multiline=True),
                    io.String.Input("transport_plan_json", default="", multiline=True),
                    io.String.Input("notes", default="", multiline=True),
                ],
                outputs=[
                    io.String.Output("td_frame_plan_json"),
                    io.String.Output("manifest_line"),
                    io.String.Output("summary_json"),
                ],
            )

        @classmethod
        def execute(
            cls,
            asset_path: str,
            transport: str,
            top_name: str,
            operator_path: str,
            asset_kind: str,
            colorspace: str,
            metadata_json: str,
            transport_plan_json: str,
            notes: str,
        ) -> io.NodeOutput:
            return io.NodeOutput(
                *_V1TD().build(
                    asset_path,
                    transport,
                    top_name,
                    operator_path,
                    asset_kind,
                    colorspace,
                    metadata_json,
                    transport_plan_json,
                    notes,
                )
            )


    class MKRV3TiXLFramePlan(_BaseV3):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="MKRV3TiXLFramePlan",
                display_name="TiXL Frame Plan (V3)",
                category="MKRShift Nodes/Addons/TiXL",
                description="V3 schema companion for TiXL frame/layer return plans.",
                search_aliases=["tixl", "tooll", "v3"],
                inputs=[
                    io.String.Input("asset_path", default=""),
                    io.Combo.Input("transport", options=["file", "ndi", "spout", "osc"], default="file"),
                    io.Combo.Input("source_kind", options=["texture", "image_sequence", "video", "mask"], default="texture"),
                    io.String.Input("layer_name", default="MKRShift Layer"),
                    io.String.Input("graph_name", default="MKRShiftBridge"),
                    io.Combo.Input("blend_mode", options=["Alpha", "Add", "Screen", "Multiply"], default="Alpha"),
                    io.String.Input("metadata_json", default="", multiline=True),
                    io.String.Input("transport_plan_json", default="", multiline=True),
                    io.String.Input("notes", default="", multiline=True),
                ],
                outputs=[
                    io.String.Output("tixl_frame_plan_json"),
                    io.String.Output("manifest_line"),
                    io.String.Output("summary_json"),
                ],
            )

        @classmethod
        def execute(
            cls,
            asset_path: str,
            transport: str,
            source_kind: str,
            layer_name: str,
            graph_name: str,
            blend_mode: str,
            metadata_json: str,
            transport_plan_json: str,
            notes: str,
        ) -> io.NodeOutput:
            return io.NodeOutput(
                *_V1TiXL().build(
                    asset_path,
                    transport,
                    source_kind,
                    layer_name,
                    graph_name,
                    blend_mode,
                    metadata_json,
                    transport_plan_json,
                    notes,
                )
            )


    class MKRShiftV3Extension(ComfyExtension):
        async def get_node_list(self) -> list[type[io.ComfyNode]]:
            return [
                MKRV3OSCMessagePlan,
                MKRV3NDIStreamPlan,
                MKRV3SpoutSenderPlan,
                MKRV3WebSocketBridgePlan,
                MKRV3TouchDesignerFramePlan,
                MKRV3TiXLFramePlan,
            ]


else:  # pragma: no cover
    class MKRShiftV3Extension:  # type: ignore[no-redef]
        pass


async def comfy_entrypoint() -> Any:  # pragma: no cover
    if ComfyExtension is None:
        raise RuntimeError("comfy_api.v0_0_2 is not available in this environment")
    return MKRShiftV3Extension()
