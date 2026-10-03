import io as bytes_io
from functools import partial

import numpy as np
import torch
from comfy_api.latest import ComfyExtension, io, ui
from comfy_execution.graph_utils import ExecutionBlocker
from PIL import Image
from typing_extensions import override

from .backends import DEFAULT_JEV_MODEL, DEVICES, LAYA_CHECKPOINTS, PROVIDERS, ImageSource, build_backend
from .images import check_images, pick_best
from .judgment import choose, score, yes_no
from .questions import lookup, parse_mapping

CATEGORY = "SystemOne"
SystemOneBackendType = io.Custom("SYSTEMONE_BACKEND")


def _text(name: str, **kwargs) -> io.String.Input:
    return io.String.Input(name, multiline=True, dynamic_prompts=False, **kwargs)


def _judgment_inputs() -> list:
    return [
        SystemOneBackendType.Input("backend"),
        _text("state", tooltip="What the model looks at: plain text, or a JSON object/array."),
        _text("instructions", tooltip="The question to answer about the state."),
    ]


JPEG_QUALITY = 85


def _to_jpeg(image: torch.Tensor, long_side: int) -> bytes:
    pixels = (image.clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
    picture = Image.fromarray(np.ascontiguousarray(pixels)).convert("RGB")
    picture.thumbnail((long_side, long_side), Image.LANCZOS)
    buffer = bytes_io.BytesIO()
    picture.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def _sources(images: torch.Tensor) -> list[ImageSource]:
    return [partial(_to_jpeg, image) for image in images]


def _image_inputs() -> list:
    return [
        SystemOneBackendType.Input("backend", tooltip="Use a Clef provider; only Clef can see images."),
        io.Image.Input("images"),
    ]


def _context_input() -> io.String.Input:
    return _text("context", optional=True, default="", tooltip="Usually the generation prompt. Sent as the state's 'prompt'.")


class SystemOneBackend(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOneBackend",
            display_name="System One Backend",
            category=CATEGORY,
            description=(
                "Pick the System One model: Laya runs locally, Jev calls the TypeSafe API (needs TYPESAFE_API_KEY), "
                "Clef calls Cloudflare Workers AI and can see images (needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN)."
            ),
            inputs=[
                io.Combo.Input("provider", options=PROVIDERS),
                io.Combo.Input("laya_checkpoint", options=list(LAYA_CHECKPOINTS)),
                io.Combo.Input("device", options=DEVICES),
                io.String.Input("jev_model", default=DEFAULT_JEV_MODEL),
            ],
            outputs=[SystemOneBackendType.Output(display_name="backend")],
        )

    @classmethod
    def execute(cls, provider, laya_checkpoint, device, jev_model) -> io.NodeOutput:
        return io.NodeOutput(build_backend(provider, laya_checkpoint, device, jev_model))


class SystemOneChoice(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOneChoice",
            display_name="System One Choice",
            category=CATEGORY,
            description="Ask the model to pick one option for the state.",
            is_output_node=True,
            inputs=[
                *_judgment_inputs(),
                _text("options", tooltip="One option per line: 'label: description' or just 'label'."),
                io.Float.Input("min_confidence", default=0.0, min=0.0, max=1.0, step=0.01),
                io.String.Input("fallback", default="", tooltip="Returned instead of the choice when confidence is below min_confidence."),
            ],
            outputs=[
                io.String.Output(display_name="choice"),
                io.Float.Output(display_name="confidence"),
                io.Boolean.Output(display_name="confident"),
                io.String.Output(display_name="report"),
            ],
        )

    @classmethod
    def execute(cls, backend, state, instructions, options, min_confidence, fallback) -> io.NodeOutput:
        result = choose(backend, state, instructions, options, min_confidence, fallback)
        return io.NodeOutput(
            result.choice, result.confidence, result.confident, result.report, ui=ui.PreviewText(result.preview)
        )


class SystemOneNoul(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOneNoul",
            display_name="System One Yes/No",
            category=CATEGORY,
            description="Ask the model how likely a yes/no statement is true for the state.",
            is_output_node=True,
            inputs=[
                *_judgment_inputs(),
                _text("true_criteria", optional=True, default=""),
                _text("false_criteria", optional=True, default=""),
                io.Float.Input("threshold", default=0.5, min=0.0, max=1.0, step=0.01),
            ],
            outputs=[
                io.Float.Output(display_name="probability"),
                io.Boolean.Output(display_name="verdict"),
                io.String.Output(display_name="report"),
            ],
        )

    @classmethod
    def execute(cls, backend, state, instructions, threshold, true_criteria="", false_criteria="") -> io.NodeOutput:
        result = yes_no(backend, state, instructions, true_criteria, false_criteria, threshold)
        return io.NodeOutput(result.probability, result.verdict, result.report, ui=ui.PreviewText(result.preview))


class SystemOneScore(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOneScore",
            display_name="System One Score",
            category=CATEGORY,
            description="Ask the model to place the state on a scale of levels.",
            is_output_node=True,
            inputs=[
                *_judgment_inputs(),
                _text("levels", tooltip="One level description per line, lowest first."),
            ],
            outputs=[
                io.Float.Output(display_name="score"),
                io.Int.Output(display_name="level"),
                io.Float.Output(display_name="confidence"),
                io.String.Output(display_name="report"),
            ],
        )

    @classmethod
    def execute(cls, backend, state, instructions, levels) -> io.NodeOutput:
        result = score(backend, state, instructions, levels)
        return io.NodeOutput(
            result.score, result.level, result.confidence, result.report, ui=ui.PreviewText(result.preview)
        )


class SystemOneMap(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOneMap",
            display_name="System One Map",
            category=CATEGORY,
            description="Turn a label into a value. For an INT level, convert it to a string first.",
            inputs=[
                io.String.Input("key", force_input=True),
                _text("mapping", tooltip="One 'key => value' per line; '* => value' is the default."),
            ],
            outputs=[io.String.Output(display_name="value")],
        )

    @classmethod
    def execute(cls, key, mapping) -> io.NodeOutput:
        return io.NodeOutput(lookup(parse_mapping(mapping), key))


class SystemOneImageCheck(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOneImageCheck",
            display_name="System One Image Check",
            category=CATEGORY,
            description="Ask a yes/no question about each image and keep only the images that pass.",
            is_output_node=True,
            inputs=[
                *_image_inputs(),
                _text("instructions", tooltip="A yes/no question about one image, e.g. 'Does the image show malformed hands?'"),
                _context_input(),
                _text("true_criteria", optional=True, default=""),
                _text("false_criteria", optional=True, default=""),
                io.Combo.Input("reject_when", options=["yes", "no"], default="yes", tooltip="Which answer drops the image."),
                io.Float.Input("threshold", default=0.5, min=0.0, max=1.0, step=0.01),
            ],
            outputs=[
                io.Image.Output(display_name="passed"),
                io.Int.Output(display_name="passed_count"),
                io.String.Output(display_name="report"),
            ],
        )

    @classmethod
    def execute(
        cls, backend, images, instructions, reject_when, threshold, context="", true_criteria="", false_criteria=""
    ) -> io.NodeOutput:
        result = check_images(
            backend, _sources(images), context, instructions,
            true_criteria, false_criteria, reject_when, threshold,
        )
        passed = images[list(result.passed_indices)] if result.passed_indices else ExecutionBlocker(None)
        return io.NodeOutput(passed, len(result.passed_indices), result.report, ui=ui.PreviewText(result.preview))


class SystemOnePickBestImage(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SystemOnePickBestImage",
            display_name="System One Pick Best Image",
            category=CATEGORY,
            description="Pick the image of a batch that best fits the instructions. Batches over 4 run as heats.",
            is_output_node=True,
            inputs=[
                *_image_inputs(),
                _text("instructions", default="Which attached image best matches the prompt in `prompt`?"),
                _context_input(),
            ],
            outputs=[
                io.Image.Output(display_name="best"),
                io.Int.Output(display_name="index"),
                io.Float.Output(display_name="confidence"),
                io.String.Output(display_name="report"),
            ],
        )

    @classmethod
    def execute(cls, backend, images, instructions, context="") -> io.NodeOutput:
        result = pick_best(backend, _sources(images), context, instructions)
        best = images[result.index : result.index + 1]
        return io.NodeOutput(best, result.index, result.confidence, result.report, ui=ui.PreviewText(result.preview))


class SystemOneExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            SystemOneBackend, SystemOneChoice, SystemOneNoul, SystemOneScore, SystemOneMap,
            SystemOneImageCheck, SystemOnePickBestImage,
        ]
