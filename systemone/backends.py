import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Protocol

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_KEY_ENV = "TYPESAFE_API_KEY"
JEV_TIMEOUT_S = 30

LAYA_CHECKPOINTS: dict[str, tuple[str, str | None]] = {
    "convaiinnovations/laya": ("convaiinnovations/laya", None),
    "convaiinnovations/laya (multilingual)": ("convaiinnovations/laya", "multilingual"),
}
DEVICES = ["auto", "mps", "cuda", "cpu"]
CLEF_MODELS = ["clef-flash", "clef"]
CLEF_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"
CLEF_ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
CLEF_TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
CLEF_TIMEOUT_S = 60
MAX_IMAGES_PER_CALL = 4
# Workers AI estimates tokens from raw request size; 4 x 384px JPEGs (~131 KB) fit, 4 x 512px (~230 KB) got a 413.
CLEF_IMAGE_BUDGET_BYTES = 150_000
CLEF_LONG_SIDES = (512, 384, 320, 256)
IMAGE_MIME = "image/jpeg"
PROVIDERS = ["laya", "jev", *CLEF_MODELS]
DEFAULT_JEV_MODEL = "jev-1.13.0"


ImageSource = Callable[[int], bytes]
"""Encodes one image as JPEG bytes with its long side at most the given pixel count."""


class Backend(Protocol):
    name: str
    supports_images: bool

    def ask(self, state: Any, questions: dict, images: list[ImageSource] | None = None) -> dict: ...


def _reject_images(backend: Backend, images: list[ImageSource] | None) -> None:
    if images:
        raise RuntimeError(f"{backend.name} cannot see images; use a Clef backend.")


def _env(name: str, backend_label: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"The {backend_label} backend needs the {name} environment variable set before starting ComfyUI.")
    return value


def _post_json(url: str, token: str, body: dict, timeout: int, api_label: str) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        snippet = error.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{api_label} API returned HTTP {error.code}: {snippet}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the {api_label} API: {error.reason}") from None


def encode_image(image_bytes: bytes, mime: str = IMAGE_MIME) -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def fit_images(images: list[ImageSource]) -> list[bytes]:
    for long_side in CLEF_LONG_SIDES:
        encoded = [image(long_side) for image in images]
        if sum(len(blob) for blob in encoded) <= CLEF_IMAGE_BUDGET_BYTES:
            return encoded
    raise RuntimeError(
        f"{len(images)} images still exceed the {CLEF_IMAGE_BUDGET_BYTES} byte Clef request budget "
        f"at a {CLEF_LONG_SIDES[-1]}px long side."
    )


_laya_agents: dict[tuple[str, str | None, str | None], Any] = {}


@dataclass(frozen=True)
class LayaBackend:
    supports_images = False

    checkpoint: str
    subfolder: str | None
    device: str | None

    @property
    def name(self) -> str:
        return f"laya:{self.checkpoint}" + (f"/{self.subfolder}" if self.subfolder else "")

    def _agent(self):
        key = (self.checkpoint, self.subfolder, self.device)
        if key not in _laya_agents:
            os.environ.setdefault("USE_TF", "0")
            try:
                import laya
            except ImportError as error:
                raise RuntimeError(
                    "The Laya backend needs the 'laya' package. Install it with "
                    "'pip install laya>=0.3.24' in ComfyUI's Python environment, or use the jev provider."
                ) from error
            _laya_agents[key] = laya.load(self.checkpoint, subfolder=self.subfolder, device=self.device)
        return _laya_agents[key]

    def ask(self, state: Any, questions: dict, images: list[ImageSource] | None = None) -> dict:
        _reject_images(self, images)
        return self._agent().predict(state, questions)["answers"]


@dataclass(frozen=True)
class JevBackend:
    supports_images = False

    model: str

    @property
    def name(self) -> str:
        return f"jev:{self.model}"

    def ask(self, state: Any, questions: dict, images: list[ImageSource] | None = None) -> dict:
        _reject_images(self, images)
        api_key = _env(JEV_KEY_ENV, "Jev")
        body = {"state": state, "model": self.model, "questions": questions}
        return _post_json(JEV_URL, api_key, body, JEV_TIMEOUT_S, "Jev")["answers"]


@dataclass(frozen=True)
class ClefBackend:
    supports_images = True

    model: str

    @property
    def name(self) -> str:
        return f"clef:{self.model}"

    def ask(self, state: Any, questions: dict, images: list[ImageSource] | None = None) -> dict:
        if images and len(images) > MAX_IMAGES_PER_CALL:
            raise RuntimeError(f"Clef accepts at most {MAX_IMAGES_PER_CALL} images per call, got {len(images)}.")
        account_id = _env(CLEF_ACCOUNT_ENV, "Clef")
        token = _env(CLEF_TOKEN_ENV, "Clef")
        body = {"model": self.model, "state": state, "questions": questions}
        if images:
            body["images"] = [encode_image(blob) for blob in fit_images(images)]
        url = CLEF_URL.format(account_id=account_id, model=self.model)
        payload = _post_json(url, token, body, CLEF_TIMEOUT_S, "Clef")
        if payload.get("success") is False:
            raise RuntimeError(f"Clef API reported failure: {payload.get('errors')}")
        return payload.get("result", payload)["answers"]


def build_backend(provider: str, laya_checkpoint: str, device: str, jev_model: str) -> Backend:
    if provider in CLEF_MODELS:
        return ClefBackend(model=provider)
    if provider == "jev":
        return JevBackend(model=jev_model.strip() or DEFAULT_JEV_MODEL)
    checkpoint, subfolder = LAYA_CHECKPOINTS[laya_checkpoint]
    return LayaBackend(checkpoint=checkpoint, subfolder=subfolder, device=None if device == "auto" else device)
