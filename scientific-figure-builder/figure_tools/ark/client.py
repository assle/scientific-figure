"""Ark client: fixed-role model integration with budget, cache, and retry.

Plan sections 5, 8, 12, 17. Tested with an injectable transport (no paid calls).
The API key is never serialized into artifacts, logs, or manifests.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

from figure_tools.ark.auth import redact
from figure_tools.ark.transport import ArkError, RateLimitError, ArkTransport
from figure_tools.state import Cache, RunState
from figure_tools.validation.image_checks import deterministic_image_checks


def file_hash(path: str | Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# Internal paid-call roles -> config model-role keys (plan section 5).
ROLE_TO_CONFIG = {
    "generation": "image_generate",
    "edits": "image_edit",
    "reference_analysis": "vision_analyze",
    "validations": "vision_validate",
    "final_validation": "vision_validate",
}


class ArkClient:
    def __init__(
        self,
        models: dict[str, dict],
        transport: ArkTransport,
        api_key: str | None = None,
        state: RunState | None = None,
        cache: Cache | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.models = models
        self.transport = transport
        self.api_key = api_key
        self.state = state
        self.cache = cache
        self.output_dir = Path(output_dir) if output_dir else None

    def _role_model(self, role: str) -> str:
        return self.models[ROLE_TO_CONFIG[role]]["model"]

    def _record_call(self, role: str) -> None:
        if self.state is not None:
            self.state.record_call(role)

    def _cache_hit(self) -> None:
        if self.state is not None:
            self.state.cache_hits += 1

    def _log_prompt(self, role: str, prompt: str) -> None:
        if self.output_dir is None:
            return
        prompts_dir = self.output_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        safe = redact(prompt, self.api_key)
        (prompts_dir / f"{role}_{_sha(prompt)[:16]}.txt").write_text(safe, encoding="utf-8")

    def _post(self, role: str, payload: dict, image_paths: list[str] | None = None,
              max_transient: int = 5) -> dict:
        attempt = 0
        while True:
            try:
                return self.transport.post(role, self._role_model(role), payload, image_paths)
            except RateLimitError:
                attempt += 1
                if self.state is not None:
                    self.state.record_retry(role, "transient")
                if attempt >= max_transient:
                    raise
                time.sleep(min(0.001 * (2 ** attempt), 0.01))

    # --- reference analysis ---------------------------------------------
    def analyze_reference_figure(self, image_path: str | Path,
                                 prompt: str | None = None,
                                 force: bool = False) -> dict[str, Any]:
        role = "reference_analysis"
        model = self._role_model(role)
        img_hash = file_hash(image_path)
        key = Cache.make_key(model, _sha(prompt or ""), {"image": img_hash}, [])
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                return json.loads(cached)
        self._record_call(role)
        resp = self._post(role, {"prompt": prompt, "image_hash": img_hash},
                          image_paths=[str(image_path)])
        if self.cache is not None:
            self.cache.put_bytes(key, json.dumps(resp).encode("utf-8"))
        return resp

    # --- image generation / edit ----------------------------------------
    def _image_meta(self, image_bytes: bytes, path: Path, role: str,
                    parameters: dict, prompt_hash: str,
                    reference_hashes: list[str], cached: bool,
                    parent_asset_id: str | None = None) -> dict[str, Any]:
        path.write_bytes(image_bytes)
        # Transparency workflow (plan section 9): if the model returned an
        # opaque image, remove the background so the asset is genuinely
        # transparent. No-op for already-transparent images (e.g. mock).
        from figure_tools.imaging.background_removal import ensure_transparency

        transparent = ensure_transparency(path)
        img = Image.open(path)
        final_bytes = path.read_bytes()
        meta: dict[str, Any] = {
            "path": str(path),
            "content_hash": "sha256:" + hashlib.sha256(final_bytes).hexdigest(),
            "pixel_dimensions": list(img.size),
            "transparent": transparent,
            "model": self._role_model(role),
            "parameters": parameters,
            "prompt_hash": prompt_hash,
            "reference_hashes": list(reference_hashes),
            "cached": cached,
        }
        if parent_asset_id is not None:
            meta["parent_asset_id"] = parent_asset_id
        return meta

    def generate_image_asset(self, prompt: str, parameters: dict,
                             output_path: str | Path,
                             reference_hashes: list[str] | None = None,
                             reference_paths: list[str] | None = None,
                             force: bool = False) -> dict[str, Any]:
        role = "generation"
        model = self._role_model(role)
        prompt_hash = _sha(prompt)
        ref_hashes = list(reference_hashes or [])
        key = Cache.make_key(model, prompt_hash, parameters, ref_hashes)
        out = Path(output_path)
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                return self._image_meta(cached, out, role, parameters, prompt_hash,
                                        ref_hashes, cached=True)
        self._record_call(role)
        resp = self._post(role, {"prompt": prompt, "parameters": parameters},
                          image_paths=list(reference_paths or []))
        image_bytes = resp["image_bytes"]
        if self.cache is not None:
            self.cache.put_bytes(key, image_bytes)
        self._log_prompt(role, prompt)
        return self._image_meta(image_bytes, out, role, parameters, prompt_hash,
                                ref_hashes, cached=False)

    def edit_image_asset(self, parent_path: str | Path, prompt: str, parameters: dict,
                         output_path: str | Path, parent_asset_id: str | None = None,
                         force: bool = False) -> dict[str, Any]:
        role = "edits"
        model = self._role_model(role)
        prompt_hash = _sha(prompt)
        parent_hash = file_hash(parent_path)
        ref_hashes = [parent_hash]
        key = Cache.make_key(model, prompt_hash, parameters, ref_hashes)
        out = Path(output_path)
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                return self._image_meta(cached, out, role, parameters, prompt_hash,
                                        ref_hashes, cached=True, parent_asset_id=parent_asset_id)
        self._record_call(role)
        resp = self._post(role, {"prompt": prompt, "parameters": parameters,
                                 "parent_hash": parent_hash},
                          image_paths=[str(parent_path)])
        image_bytes = resp["image_bytes"]
        if self.cache is not None:
            self.cache.put_bytes(key, image_bytes)
        self._log_prompt(role, prompt)
        return self._image_meta(image_bytes, out, role, parameters, prompt_hash,
                                ref_hashes, cached=False, parent_asset_id=parent_asset_id)

    # --- multimodal validation ------------------------------------------
    def validate_image_asset(self, image_path: str | Path,
                             physical_size_mm: tuple[float, float] | None = None,
                             checks: list[str] | None = None,
                             force: bool = False) -> dict[str, Any]:
        role = "validations"
        model = self._role_model(role)
        img_hash = file_hash(image_path)
        key = Cache.make_key(model, img_hash, {"checks": list(checks or [])}, [])

        det_checks = deterministic_image_checks(image_path, physical_size_mm)
        for c in det_checks:
            c["scope"] = f"asset:{Path(image_path).name}"

        multimodal: dict | None = None
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                multimodal = json.loads(cached)
        if multimodal is None:
            self._record_call(role)
            multimodal = self._post(role, {"image_hash": img_hash,
                                           "checks": list(checks or [])},
                                    image_paths=[str(image_path)])
            if self.cache is not None:
                self.cache.put_bytes(key, json.dumps(multimodal).encode("utf-8"))

        mm_checks = multimodal.get("checks", [])
        for c in mm_checks:
            c["scope"] = f"asset:{Path(image_path).name}"
            c.setdefault("level", "error")

        all_checks = det_checks + mm_checks
        errors = sum(1 for c in all_checks if c["level"] == "error" and c["status"] == "fail")
        warnings = sum(1 for c in all_checks if c["level"] == "warning" and c["status"] == "fail")
        passed = sum(1 for c in all_checks if c["status"] == "pass")
        run_id = self.state.run_id if self.state else f"asset:{Path(image_path).name}"
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "checks": all_checks,
            "summary": {
                "errors": errors,
                "warnings": warnings,
                "passed": passed,
                "blocking": errors > 0,
            },
        }

    # --- upload disclosure ----------------------------------------------
    def disclose_uploads(self, paths: list[str | Path]) -> list[dict[str, Any]]:
        return [
            {"path": str(p), "content_hash": file_hash(p), "reason": "reference upload"}
            for p in paths
        ]
