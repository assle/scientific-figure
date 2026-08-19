"""Real Volcengine Ark transport (plan sections 8, 12, 17).

Uses the official `volcenginesdkarkruntime` SDK (OpenAI-compatible). Image
generation and editing use `client.images.generate`; reference analysis and
multimodal validation use `client.chat.completions.create` with image content.
The API key is read from the environment and never serialized.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from figure_tools.ark.contracts import (
    DEFAULT_VALIDATION_INSTRUCTION as _DEFAULT_VALIDATION_INSTRUCTION,
    extract_json as _extract_json,
    vision_prompt,
)
from figure_tools.ark.transport import ArkError, RateLimitError, ArkTransport

try:
    from volcenginesdkarkruntime import Ark
    from volcenginesdkarkruntime._exceptions import (
        ArkAPIConnectionError,
        ArkAPITimeoutError,
        ArkRateLimitError,
    )
    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - SDK is an optional extra
    _SDK_AVAILABLE = False
    Ark = None  # type: ignore


def _data_url(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


class RealArkTransport(ArkTransport):
    # Plan-routed OpenAI-compatible base URLs (plan is selected by base URL).
    AGENT_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"      # image gen/edit
    CODING_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"   # vision chat

    def __init__(self, api_key: str | None = None, coding_api_key: str | None = None,
                 agent_base_url: str | None = None, coding_base_url: str | None = None) -> None:
        if not _SDK_AVAILABLE:
            raise ArkError(
                "volcenginesdkarkruntime is not installed; "
                "install with: uv pip install 'volcengine-python-sdk[ark]'"
            )
        import os

        # Plan routing: plan is bound to the API key AND selected by base URL.
        #   agent plan  -> image generation / editing  (ARK_API_KEY, .../api/plan/v3)
        #   coding plan -> vision analysis / validation (ARK_API_KEY_CODING, .../api/coding/v3)
        agent_key = api_key or os.environ.get("ARK_API_KEY")
        if not agent_key:
            raise ArkError("ARK_API_KEY is not set")
        coding_key = coding_api_key or os.environ.get("ARK_API_KEY_CODING") or agent_key
        agent_base = (agent_base_url or os.environ.get("ARK_AGENT_BASE_URL")
                      or self.AGENT_BASE_URL)
        coding_base = (coding_base_url or os.environ.get("ARK_CODING_BASE_URL")
                       or self.CODING_BASE_URL)
        self._clients = {
            "agent": self._make_client(agent_key, agent_base),
            "coding": self._make_client(coding_key, coding_base),
        }

    @staticmethod
    def _make_client(api_key: str, base_url: str):
        return Ark(api_key=api_key, base_url=base_url)  # type: ignore[misc]

    @staticmethod
    def _plan_for(role: str) -> str:
        return "agent" if role in ("generation", "edits") else "coding"

    def post(self, role: str, model: str, payload: dict,
             image_paths: list[str] | None = None) -> dict[str, Any]:
        try:
            if role in ("generation", "edits"):
                return self._image(role, model, payload, image_paths)
            if role in ("reference_analysis", "validations", "final_validation"):
                return self._vision(role, model, payload, image_paths or [])
            raise ArkError(f"unknown role {role!r}")
        except (ArkRateLimitError, ArkAPIConnectionError, ArkAPITimeoutError) as e:
            raise RateLimitError(f"transient Ark error: {e}") from e
        except Exception as e:  # noqa: BLE001
            if "Ark" in type(e).__name__:
                raise ArkError(str(e)) from e
            raise

    def _image(self, role, model, payload, image_paths):
        params = payload.get("parameters", {})
        kwargs: dict[str, Any] = {
            "model": model,
            "prompt": payload["prompt"],
            "response_format": "b64_json",
            "output_format": "png",
            "watermark": False,
            # Seedream requires >= 3,686,400 px (1920x1920); default to 2048x2048.
            "size": params.get("size") or "2048x2048",
        }
        if params.get("seed") is not None:
            kwargs["seed"] = params["seed"]
        if role == "edits" and image_paths:
            kwargs["image"] = _data_url(image_paths[0])
        elif image_paths:
            kwargs["image"] = [_data_url(p) for p in image_paths]
        resp = self._clients[self._plan_for(role)].images.generate(**kwargs)
        if getattr(resp, "error", None):
            raise ArkError(f"Ark image error: {resp.error}")
        if not resp.data:
            raise ArkError("Ark returned no image data")
        b64 = resp.data[0].b64_json
        if not b64:
            raise ArkError("Ark returned no b64_json (url-only not supported here)")
        image_bytes = base64.b64decode(b64)
        return {"image_bytes": image_bytes, "model": model,
                "seed": kwargs.get("seed")}

    def _vision(self, role, model, payload, image_paths):
        prompt = vision_prompt(role, payload)
        content: list[dict] = [{"type": "text", "text": prompt}]
        for p in image_paths:
            content.append({"type": "image_url", "image_url": {"url": _data_url(p)}})
        resp = self._clients[self._plan_for(role)].chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or ""
        return _extract_json(text)
