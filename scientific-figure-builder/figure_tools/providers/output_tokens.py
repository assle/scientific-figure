"""Phase-local structured output allowances, independent of request timing."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

PHASES = ('intake', 'planning', 'review_and_repair')
DEFAULT_PHASE_OUTPUT_TOKENS = 8192


def positive_tokens(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f'{label} must be a positive integer')
    return value


@dataclass(frozen=True)
class OutputTokenPolicy:
    initial_tokens: int = DEFAULT_PHASE_OUTPUT_TOKENS
    phase_initial_tokens: dict[str, int] = field(default_factory=dict)
    max_tokens: int | None = None

    def initial(self, phase: str, remembered: int = 0) -> int:
        value = max(self.phase_initial_tokens.get(phase, self.initial_tokens), remembered)
        return min(value, self.max_tokens) if self.max_tokens is not None else value

    def expand(self, current: int) -> int:
        value = current * 2
        return min(value, self.max_tokens) if self.max_tokens is not None else value

    @classmethod
    def resolve(cls, *overrides: Any, known_limit: int | None = None) -> OutputTokenPolicy:
        initial = DEFAULT_PHASE_OUTPUT_TOKENS
        phases: dict[str, int] = {}
        maximum = None
        for override in overrides:
            if override is None:
                continue
            if not isinstance(override, Mapping):
                raise ValueError('output_tokens must be a mapping')
            unknown = set(override) - {'initial_tokens', 'phase_initial_tokens', 'max_tokens'}
            if unknown:
                raise ValueError(f'unknown output_tokens fields: {sorted(unknown)}')
            if 'initial_tokens' in override:
                initial = positive_tokens(override['initial_tokens'], 'initial_tokens')
            if 'max_tokens' in override:
                maximum = positive_tokens(override['max_tokens'], 'max_tokens')
            if 'phase_initial_tokens' in override:
                values = override['phase_initial_tokens']
                if not isinstance(values, Mapping) or set(values) - set(PHASES):
                    raise ValueError(f'phase_initial_tokens must map known phases: {PHASES}')
                phases.update({name: positive_tokens(value, name) for name, value in values.items()})
        if known_limit is not None:
            maximum = min(maximum, known_limit) if maximum is not None else known_limit
        return cls(initial, phases, maximum)


def model_output_limit(provider: Mapping[str, Any], model: str) -> int | None:
    # Official advertised maximum is 384K; use a conservative decimal bound.
    # https://api-docs.deepseek.com/quick_start/pricing/ (checked 2026-09-07)
    if (urlparse(str(provider.get('base_url', ''))).hostname == 'api.deepseek.com'
            and model in {'deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-v4-flash-vision-exp'}):
        return 384000
    return None
