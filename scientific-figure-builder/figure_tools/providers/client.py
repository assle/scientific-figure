"""Provider client: fixed-role model integration with budget, cache, and retry.

Plan sections 5, 8, 12, 17. Tested with an injectable transport (no paid calls).
The API key is never serialized into artifacts, logs, or manifests.
"""

from __future__ import annotations

import io
import json
import threading
import uuid
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from figure_tools.providers.auth import SecretRedactor, sanitize_error
from figure_tools.provenance import hash_bytes, hash_file
from figure_tools.providers.transport import (
    IncompleteStructuredResponseError,
    ProviderError,
    ProviderTransport,
    RateLimitError,
    RequestError,
    ROLE_TO_MODEL_CONFIG,
    model_config_for_role,
)
from figure_tools.state import BudgetExceeded, Cache, RunState
from figure_tools.providers.request_policy import RequestPolicy
from figure_tools.providers.output_tokens import OutputTokenPolicy
from figure_tools.providers.request_session import CURRENT_REQUEST, RequestSession, retry_delay
from figure_tools.validation.image_checks import deterministic_image_checks
from figure_tools.validation.summary import summarize_checks


def _sha(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


class ProviderClient:
    def __init__(
        self,
        models: dict[str, dict],
        transport: ProviderTransport,
        api_key: str | None = None,
        api_keys: Iterable[str] | None = None,
        redactor: SecretRedactor | None = None,
        state: RunState | None = None,
        cache: Cache | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.models = models
        self.transport = transport
        self.api_key = api_key
        self.api_keys = tuple(dict.fromkeys(
            key for key in (api_key, *(api_keys or ())) if key
        ))
        self.redactor = redactor or SecretRedactor(self.api_keys)
        self.state = state
        self.cache = cache
        self.output_dir = Path(output_dir) if output_dir else None
        self._lock = threading.RLock()
        self.cancelled = threading.Event()
        self.progress_callback = None

    def _role_model(self, role: str) -> str:
        resolved = model_config_for_role(self.models, role)
        config_role = ROLE_TO_MODEL_CONFIG.get(role, role)
        model_config = resolved[1] if resolved is not None else None
        if not model_config or not model_config.get("model"):
            raise ProviderError(
                f"model role {config_role!r} is not configured for {role!r}"
            )
        return str(model_config["model"])

    def generation_capabilities(self) -> dict[str, bool]:
        return dict(self.transport.capabilities())

    def _record_call(self, role: str) -> None:
        if self.state is not None:
            budget_role = role
            if role == "edits" and "image_edit" not in self.models:
                budget_role = "generation"
            with self._lock:
                self.state.record_call(budget_role)

    def _cache_hit(self) -> None:
        if self.state is not None:
            with self._lock:
                self.state.cache_hits += 1

    def _log_prompt(self, role: str, prompt: str) -> None:
        if self.output_dir is None:
            return
        prompts_dir = self.output_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        safe = self.redactor.redact_text(prompt)
        (prompts_dir / f"{role}_{_sha(prompt)[:16]}.txt").write_text(safe, encoding="utf-8")

    def clean_error(self, error: BaseException | str) -> str:
        """Return a safe message without changing exception propagation.

        Callers decide whether an exception should be retried, surfaced, or
        converted to a protocol error; this method only performs redaction.
        """

        return sanitize_error(error, self.redactor.secrets)

    def _persist(self) -> None:
        if self.state is not None and self.output_dir is not None:
            self.state.save(self.output_dir / "run_state.json")

    def _post(self, role: str, payload: dict, image_paths: list[str] | None = None,
              max_transient: int | None = None) -> dict:
        model = self._role_model(role)
        policy_factory = getattr(self.transport, "request_policy", None)
        policy = policy_factory(role) if policy_factory else RequestPolicy.resolve(role)
        if max_transient is not None:
            policy = RequestPolicy.resolve(role, policy.to_dict(), {"max_attempts": max_transient})
        route = model_config_for_role(self.models, role)
        provider = str(route[1].get("provider", "unknown")) if route else "unknown"
        phase = str(payload.get("phase", role))
        invocation_id = uuid.uuid4().hex
        attempt_started = time.monotonic()
        attempts = 0
        retries = 0
        pending_retry = False
        request_payload = dict(payload)
        output_policy = None
        if role == "phase_reasoning":
            output_factory = getattr(self.transport, "output_token_policy", None)
            output_policy = output_factory(role) if output_factory else OutputTokenPolicy.resolve(
                route[1].get("output_tokens") if route else None
            )
            with self._lock:
                remembered = self.state.output_tokens_for(phase, provider, model) if self.state is not None else 0
            request_payload["max_output_tokens"] = output_policy.initial(phase, remembered)

        def progress(details: dict) -> None:
            safe = self.redactor.redact_text(json.dumps({
                "invocation_id": invocation_id,
                "role": role, "phase": phase, "provider": provider, "model": model,
                "attempt": attempts, "policy": policy.to_dict(), "output_usage": session.output_usage, **details,
            }, default=str))
            snapshot = json.loads(safe)
            with self._lock:
                if self.state is not None:
                    self.state.provider_status[role] = snapshot
                    self._persist()
            if self.progress_callback is not None:
                self.progress_callback(snapshot)

        def dispatch() -> None:
            nonlocal attempts, pending_retry, attempt_started
            session.check()
            with self._lock:
                self._record_call(role)
                if output_policy is not None and self.state is not None:
                    self.state.record_output_tokens(phase, provider, model, request_payload["max_output_tokens"])
                attempts += 1
                attempt_started = time.monotonic()
                if self.state is not None:
                    if pending_retry:
                        self.state.record_retry(role, "transient")
                    self.state.record_audit("provider_attempt_started", {
                        "invocation_id": invocation_id,
                        "role": role, "attempt": attempts, "phase": phase,
                        "provider": provider, "model": model,
                        **({"max_output_tokens": request_payload["max_output_tokens"]} if output_policy else {}),
                    })
                pending_retry = False
                session.report(state="awaiting_response", stop_reason=None,
                               **({"max_output_tokens": request_payload["max_output_tokens"]} if output_policy else {}))

        def audit(event: str, details: dict) -> None:
            safe = json.loads(self.redactor.redact_text(json.dumps({
                "invocation_id": invocation_id, "role": role, "attempt": attempts, **details,
            }, default=str)))
            with self._lock:
                if self.state is not None:
                    self.state.record_audit(event, safe)
                    self._persist()

        def send_attempt() -> dict:
            before = attempts
            error = None
            session.output_usage = None
            try:
                if not getattr(self.transport, "accounts_at_dispatch", False):
                    dispatch()
                return self.transport.post(role, model, request_payload, image_paths)
            except BaseException as exc:
                error = exc
                raise
            finally:
                if attempts > before:
                    audit("provider_attempt_finished", {
                        "elapsed_seconds": time.monotonic() - attempt_started,
                        "output_usage": session.output_usage,
                        "http_status": getattr(error, "status", None) or session.status.get("http_status"),
                        "request_id": getattr(error, "request_id", None) or session.status.get("request_id"),
                        "stop_reason": getattr(error, "category", "incomplete" if isinstance(error, IncompleteStructuredResponseError) else "provider_error") if error else "completed",
                        "last_error": self.clean_error(error)[:2000] if error else None,
                        "submission": getattr(error, "submission", "submitted"),
                    })

        session = RequestSession(policy, dispatch=dispatch, progress=progress, cancelled=self.cancelled)
        token = CURRENT_REQUEST.set(session)
        try:
            while True:
                session.check()
                try:
                    result = send_attempt()
                    audit("provider_invocation_finished", {"stop_reason": "completed"})
                    session.report(state="completed", stop_reason="completed")
                    return result
                except IncompleteStructuredResponseError as exc:
                    if exc.reason != "max_output_tokens" or self.state is None or role not in self.state.budget:
                        raise
                    if self.state.calls_remaining(role) == 0:
                        raise BudgetExceeded(f"budget for {role!r} exhausted after incomplete response") from exc
                    next_limit = output_policy.expand(exc.attempted_max_output_tokens) if output_policy else exc.attempted_max_output_tokens * 2
                    if next_limit <= exc.attempted_max_output_tokens:
                        raise RequestError("structured output reached model/configured token ceiling", category="output_limit_exhausted") from exc
                    with self._lock:
                        self.state.record_audit("structured_output_expanded", {
                            "invocation_id": invocation_id, "phase": phase,
                            "provider": provider, "model": model, "role": role,
                            "previous_max_output_tokens": exc.attempted_max_output_tokens,
                            "next_max_output_tokens": next_limit,
                        })
                        self._persist()
                    request_payload["max_output_tokens"] = next_limit
                except RequestError as exc:
                    session.report(state="failed", last_error=self.clean_error(exc),
                                   category=exc.category, http_status=exc.status,
                                   request_id=exc.request_id, submission=exc.submission)
                    if not exc.retryable:
                        raise
                    if retries >= policy.max_attempts - 1:
                        raise RequestError(f"attempt limit exhausted: {self.clean_error(exc)}",
                                           category="attempts_exhausted", status=exc.status) from exc
                    # Check before sleeping; the atomic dispatch check remains authoritative.
                    budget_role = "generation" if role == "edits" and "image_edit" not in self.models else role
                    if self.state is not None and budget_role in self.state.budget and self.state.calls_remaining(budget_role) == 0:
                        raise BudgetExceeded(f"budget for {budget_role!r} exhausted after {self.clean_error(exc)}") from exc
                    delay = retry_delay(policy, retries, exc.retry_after)
                    if delay >= session.remaining:
                        raise RequestError(f"retry delay exceeds invocation deadline: {self.clean_error(exc)}", category="deadline_exhausted") from exc
                    audit("provider_retry_scheduled", {"selected_delay": delay, "reason": exc.category})
                    session.report(state="backoff", selected_delay=delay)
                    if session.cancelled.wait(delay):
                        session.check()
                    retries += 1
                    pending_retry = True
        except BaseException as exc:
            category = getattr(exc, "category", "budget_exhausted" if isinstance(exc, BudgetExceeded) else "provider_error")
            audit("provider_invocation_finished", {"stop_reason": category, "last_error": self.clean_error(exc)[:2000]})
            session.report(state="remote_outcome_unknown" if category in (
                "inactivity_timeout", "deadline_exhausted", "connection_error", "stream_interrupted", "cancelled"
            ) else "failed", stop_reason=category, last_error=self.clean_error(exc))
            if isinstance(exc, Exception):
                exc.args = (self.clean_error(f"{phase}: provider={provider}, model={model}, attempts={attempts}, {category}: {exc}"),)
            raise
        finally:
            CURRENT_REQUEST.reset(token)

    def run_phase_worker(
        self,
        phase: str,
        prompt: str,
        context: dict[str, Any],
        allowed_tools: list[str],
        fallback_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        """Run one isolated reasoning phase and return its JSON artifact."""
        role = "phase_reasoning"
        self._log_prompt(f"phase_{phase}", prompt)
        result = self._post(role, {
            "phase": phase,
            "prompt": prompt,
            "context": context,
            "allowed_tools": allowed_tools,
            "fallback_artifact": fallback_artifact,
        })
        if not isinstance(result, dict):
            raise ProviderError("phase worker response must be a JSON object")
        return result

    # --- reference analysis ---------------------------------------------
    def analyze_reference_figure(self, image_path: str | Path,
                                 prompt: str | None = None,
                                 force: bool = False) -> dict[str, Any]:
        role = "reference_analysis"
        model = self._role_model(role)
        img_hash = hash_file(image_path)
        key = Cache.make_key(model, _sha(prompt or ""), {"image": img_hash}, [])
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                return json.loads(cached)
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

        if parameters.get("preserve_background"):
            with Image.open(path) as original:
                rgba = original.convert("RGBA")
                transparent = rgba.getchannel("A").getextrema() != (255, 255)
                rgba.save(path)
        else:
            transparent = ensure_transparency(path)
        img = Image.open(path)
        final_bytes = path.read_bytes()
        seed = parameters.get("seed") if isinstance(parameters, dict) else None
        meta: dict[str, Any] = {
            "path": str(path),
            "content_hash": hash_bytes(final_bytes),
            "pixel_dimensions": list(img.size),
            "transparent": transparent,
            "model": self._role_model(role),
            "parameters": parameters,
            "prompt_hash": prompt_hash,
            "reference_hashes": list(reference_hashes),
            "provenance": {
                "endpoint_id": self._role_model(role),
                "seed": seed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "cached": cached,
        }
        if parent_asset_id is not None:
            meta["parent_asset_id"] = parent_asset_id
        return meta

    def generate_image_asset(self, prompt: str, parameters: dict,
                             output_path: str | Path,
                             reference_hashes: list[str] | None = None,
                             reference_paths: list[str] | None = None,
                             reference_descriptors: list[dict[str, Any]] | None = None,
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
        resp = self._post(role, {
            "prompt": prompt,
            "parameters": parameters,
            "references": list(reference_descriptors or []),
        },
                          image_paths=list(reference_paths or []))
        image_bytes = resp["image_bytes"]
        if self.cache is not None:
            self.cache.put_bytes(key, image_bytes)
        self._log_prompt(role, prompt)
        return self._image_meta(image_bytes, out, role, parameters, prompt_hash,
                                ref_hashes, cached=False)

    def edit_image_asset(self, parent_path: str | Path, prompt: str, parameters: dict,
                         output_path: str | Path, parent_asset_id: str | None = None,
                         mask_path: str | Path | None = None,
                         force: bool = False) -> dict[str, Any]:
        role = "edits"
        model = self._role_model(role)
        prompt_hash = _sha(prompt)
        parent_hash = hash_file(parent_path)
        ref_hashes = [parent_hash]
        image_paths = [str(parent_path)]
        if mask_path is not None:
            ref_hashes.append(hash_file(mask_path))
            image_paths.append(str(mask_path))
        key = Cache.make_key(model, prompt_hash, parameters, ref_hashes)
        out = Path(output_path)
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                return self._image_meta(cached, out, role, parameters, prompt_hash,
                                        ref_hashes, cached=True, parent_asset_id=parent_asset_id)
        resp = self._post(role, {"prompt": prompt, "parameters": parameters,
                                 "parent_hash": parent_hash,
                                 "mask_hash": ref_hashes[1] if mask_path is not None else None},
                          image_paths=image_paths)
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
        img_hash = hash_file(image_path)
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
        run_id = self.state.run_id if self.state else f"asset:{Path(image_path).name}"
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "checks": all_checks,
            "summary": summarize_checks(all_checks),
        }

    # --- multimodal final-figure validation ----------------------------
    def validate_final_figure(
        self,
        image_path: str | Path,
        physical_size_mm: tuple[float, float] | None = None,
        checks: list[str] | None = None,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """Run the multimodal vision check on the fully composed figure.

        Returns only the multimodal checks (deterministic checks are handled by
        the final-checks module). Uses the ``final_validation`` role so it is
        budgeted independently from per-asset validations.
        """
        role = "final_validation"
        model = self._role_model(role)
        img_hash = hash_file(image_path)
        key = Cache.make_key(model, img_hash, {"checks": list(checks or [])}, [])

        multimodal: dict | None = None
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                multimodal = json.loads(cached)
        if multimodal is None:
            multimodal = self._post(role, {"image_hash": img_hash,
                                           "checks": list(checks or [])},
                                   image_paths=[str(image_path)])
            if self.cache is not None:
                self.cache.put_bytes(key, json.dumps(multimodal).encode("utf-8"))
        return list(multimodal.get("checks", []))

    # --- local-region VLM verification ---------------------------------
    def verify_local_region(
        self,
        crop_path: str | Path,
        issue_type: str,
        context: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        """Ask the vision model to confirm a localized suspected issue.

        Uses the ``validations`` role (same model as final validation). The
        caller passes the enlarged evidence crop plus geometry context. Returns
        the model's strict-JSON verdict (confirmed/confidence/...).
        """
        role = "validations"
        model = self._role_model(role)
        img_hash = hash_file(crop_path)
        payload = {"mode": "local_region", "issue_type": issue_type,
                   "context": context}
        key = Cache.make_key(model, img_hash, payload, [])
        if not force and self.cache is not None:
            cached = self.cache.get_bytes(key)
            if cached is not None:
                self._cache_hit()
                return json.loads(cached)
        resp = self._post(role, payload, image_paths=[str(crop_path)])
        if self.cache is not None:
            self.cache.put_bytes(key, json.dumps(resp).encode("utf-8"))
        return resp

    # --- upload disclosure ----------------------------------------------
    def disclose_uploads(self, paths: list[str | Path]) -> list[dict[str, Any]]:
        return [
            {"path": str(p), "content_hash": hash_file(p), "reason": "reference upload"}
            for p in paths
        ]
