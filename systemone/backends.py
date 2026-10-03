import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_KEY_ENV = "TYPESAFE_API_KEY"
JEV_TIMEOUT_S = 30

LAYA_CHECKPOINTS: dict[str, tuple[str, str | None]] = {
    "convaiinnovations/laya": ("convaiinnovations/laya", None),
    "convaiinnovations/laya (multilingual)": ("convaiinnovations/laya", "multilingual"),
}
DEVICES = ["auto", "mps", "cuda", "cpu"]
PROVIDERS = ["laya", "jev"]
DEFAULT_JEV_MODEL = "jev-1.13.0"


class Backend(Protocol):
    name: str

    def ask(self, state: Any, questions: dict) -> dict: ...


_laya_agents: dict[tuple[str, str | None, str | None], Any] = {}


@dataclass(frozen=True)
class LayaBackend:
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

    def ask(self, state: Any, questions: dict) -> dict:
        return self._agent().predict(state, questions)["answers"]


@dataclass(frozen=True)
class JevBackend:
    model: str

    @property
    def name(self) -> str:
        return f"jev:{self.model}"

    def ask(self, state: Any, questions: dict) -> dict:
        api_key = os.environ.get(JEV_KEY_ENV, "").strip()
        if not api_key:
            raise RuntimeError(f"The Jev backend needs the {JEV_KEY_ENV} environment variable set before starting ComfyUI.")
        body = json.dumps({"state": state, "model": self.model, "questions": questions}).encode()
        request = urllib.request.Request(
            JEV_URL,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=JEV_TIMEOUT_S) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            snippet = error.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Jev API returned HTTP {error.code}: {snippet}") from None
        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not reach the Jev API: {error.reason}") from None
        return payload["answers"]


def build_backend(provider: str, laya_checkpoint: str, device: str, jev_model: str) -> Backend:
    if provider == "jev":
        return JevBackend(model=jev_model.strip() or DEFAULT_JEV_MODEL)
    checkpoint, subfolder = LAYA_CHECKPOINTS[laya_checkpoint]
    return LayaBackend(checkpoint=checkpoint, subfolder=subfolder, device=None if device == "auto" else device)
