"""Cohesive runtime construction for lifecycle adapters and tests."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from figure_tools.config import load_config
from figure_tools.install_paths import APP_NAME, PathEnvironment
from figure_tools.phase_workers import ProviderPhaseWorker, StructuredPhaseWorker
from figure_tools.provider_configuration import (
    configured_model_routes,
    normalize_providers,
)
from figure_tools.providers.auth import (
    SecretRedactor,
    SecretStore,
    default_secret_store,
    resolve_provider_credentials,
)
from figure_tools.providers.client import ProviderClient
from figure_tools.providers.generic_transport import ProviderRouter
from figure_tools.providers.transport import MockProviderTransport, model_config_for_role
from figure_tools.run_store import RunStore
from figure_tools.state import Cache, RunState


DEFAULT_BUDGET = {
    "phase_reasoning": 10,
    "reference_analysis": 1,
    "generation": 5,
    "edits": 2,
    "validations": 5,
    "final_validation": 1,
}

_UNSET = object()


class RuntimeContextError(RuntimeError):
    """A Runtime Context construction failure with a redacted message."""


def default_runtime_cache_dir() -> Path:
    explicit = os.environ.get("SCIENTIFIC_FIGURE_CACHE_DIR")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            raise ValueError("SCIENTIFIC_FIGURE_CACHE_DIR must be an absolute path")
        return path
    return PathEnvironment.from_environ().cache_root / APP_NAME / "runtime"


def load_run_state(path: Path, run_id: str, budget: dict[str, int]) -> RunState:
    if path.is_file():
        return RunState.load(path)
    return RunState(run_id=run_id, budget=budget)


@dataclass(frozen=True)
class RuntimeContext:
    project_dir: Path
    run_dir: Path
    effective_config: dict[str, Any]
    models: dict[str, dict[str, Any]]
    providers: dict[str, dict[str, Any]]
    credentials: dict[str, Any]
    state: RunState
    cache: Cache
    client: ProviderClient
    worker: Any
    store: RunStore
    offline: bool


class RuntimeContextFactory:
    """Resolve all runtime-owned objects once from project and run locations."""

    def __init__(
        self,
        *,
        config_loader: Callable[[str | Path], dict[str, Any]] = load_config,
        secret_store: SecretStore | None | object = _UNSET,
        environ: Mapping[str, str] | None = None,
        transport_factory: Callable[..., Any] = ProviderRouter,
        cache_factory: Callable[[Path], Cache] = Cache,
        state_loader: Callable[[Path, str, dict[str, int]], RunState] = load_run_state,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.config_loader = config_loader
        self.secret_store: SecretStore | None = (
            default_secret_store()
            if secret_store is _UNSET
            else cast(SecretStore | None, secret_store)
        )
        self.environ = os.environ if environ is None else environ
        self.transport_factory = transport_factory
        self.cache_factory = cache_factory
        self.state_loader = state_loader
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None

    def create(
        self,
        project_dir: str | Path,
        run_dir: str | Path,
    ) -> RuntimeContext:
        project_path = Path(project_dir)
        run_path = Path(run_dir)
        store = RunStore(run_path)
        store.ensure_structure()

        effective_config = self.config_loader(project_path)
        raw_providers = effective_config.get("providers")
        provider_mapping = raw_providers if isinstance(raw_providers, Mapping) else {}
        providers = normalize_providers(provider_mapping)
        models = configured_model_routes(
            effective_config,
            environ=self.environ,
        )
        credentials = resolve_provider_credentials(
            providers,
            secret_store=self.secret_store,
            environ=self.environ,
        )
        referenced_providers = {
            str(route.get("provider"))
            for route in models.values()
            if route.get("provider")
        }
        live_credentials = {
            provider_id: credential
            for provider_id, credential in credentials.items()
            if provider_id in referenced_providers
        }
        offline = not bool(live_credentials)
        redactor = SecretRedactor(item.value for item in live_credentials.values())
        if offline:
            transport = MockProviderTransport()
            if not models:
                models = {
                    "image_generate": {"model": "mock"},
                    "image_edit": {"model": "mock"},
                    "vision_analyze": {"model": "mock"},
                    "vision_validate": {"model": "mock"},
                }
            budget: dict[str, int] = {}
        else:
            try:
                transport = self.transport_factory(
                    models,
                    providers,
                    credentials=live_credentials,
                    redactor=redactor,
                )
            except Exception as exc:  # adapters may echo credentials in failures
                raise RuntimeContextError(redactor.safe_exception(exc)) from exc
            budget = dict(DEFAULT_BUDGET)
            if "phase_reasoning" not in models:
                budget.pop("phase_reasoning", None)
            if "image_edit" not in models:
                budget.pop("edits", None)

        state = self.state_loader(
            run_path / "run_state.json",
            run_path.name,
            budget,
        )
        cache = self.cache_factory(self.cache_dir or default_runtime_cache_dir())
        api_keys = [credential.value for credential in live_credentials.values()]
        client = ProviderClient(
            models,
            transport,
            api_key=api_keys[0] if api_keys else None,
            api_keys=api_keys,
            redactor=redactor,
            state=state,
            cache=cache,
            output_dir=run_path,
        )
        worker = (
            ProviderPhaseWorker(client)
            if model_config_for_role(models, "phase_reasoning") is not None
            else StructuredPhaseWorker()
        )
        return RuntimeContext(
            project_dir=project_path,
            run_dir=run_path,
            effective_config=effective_config,
            models=models,
            providers=providers,
            credentials=live_credentials,
            state=state,
            cache=cache,
            client=client,
            worker=worker,
            store=store,
            offline=offline,
        )


__all__ = [
    "DEFAULT_BUDGET",
    "RuntimeContext",
    "RuntimeContextError",
    "RuntimeContextFactory",
    "default_runtime_cache_dir",
    "load_run_state",
]
