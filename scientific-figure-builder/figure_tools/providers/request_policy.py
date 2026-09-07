"""Validated waiting policy shared by configuration and Provider execution."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from typing import Any


@dataclass(frozen=True)
class RequestPolicy:
    connect_timeout: float = 15
    status_interval: float = 120
    inactivity_timeout: float = 600
    total_timeout: float = 1800
    max_attempts: int = 3
    backoff_base: float = 2
    backoff_cap: float = 30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def resolve(cls, role: str, *overrides: Any) -> RequestPolicy:
        values = cls().to_dict()
        if role in ('generation', 'edits', 'image_generate', 'image_edit'):
            values['inactivity_timeout'] = 30
        for override in overrides:
            if override is None:
                continue
            if not isinstance(override, Mapping):
                raise ValueError('request_policy must be a mapping')
            for key, value in override.items():
                if key not in values:
                    raise ValueError(f'unknown request_policy field: {key}')
                if key == 'max_attempts':
                    if type(value) is not int or value < 1:
                        raise ValueError('max_attempts must be a positive integer')
                elif (isinstance(value, bool) or not isinstance(value, (int, float))
                      or not math.isfinite(value) or value < 0
                      or (value == 0 and key not in ('backoff_base', 'backoff_cap'))):
                    raise ValueError(f'{key} must be a finite positive duration (backoff may be zero)')
                values[key] = value
        if values['backoff_cap'] < values['backoff_base']:
            raise ValueError('backoff_cap must be at least backoff_base')
        return cls(**values)
