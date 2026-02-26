"""Configuration manager — load/save JSON, merge with defaults."""
from __future__ import annotations

import copy
import json
import logging
import typing
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

from .defaults import DEFAULT_CONFIG
from .schema import TuposcanConfig

log = logging.getLogger(__name__)


def _enum_serialiser(obj: Any) -> Any:
    """JSON default handler for enum values."""
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def merge_dataclass(dc: Any, data: dict) -> Any:
    """Recursively update a dataclass instance from a dict."""
    # Resolve actual types (handles 'from __future__ import annotations')
    try:
        hints = get_type_hints(type(dc))
    except Exception:
        hints = {}

    for f in fields(dc):
        if f.name not in data:
            continue
        val = data[f.name]
        current = getattr(dc, f.name)
        if is_dataclass(current) and isinstance(val, dict):
            merge_dataclass(current, val)
        else:
            resolved_type = hints.get(f.name)
            # Check if it's a generic type (list, dict, etc.)
            if resolved_type is not None and hasattr(resolved_type, "__args__"):
                setattr(dc, f.name, val)
            else:
                # Try to coerce enums
                field_type = type(current)
                if hasattr(field_type, "__members__"):
                    try:
                        setattr(dc, f.name, field_type(val))
                    except (ValueError, KeyError):
                        log.warning("Unknown enum value %r for %s, keeping default", val, f.name)
                else:
                    setattr(dc, f.name, val)
    return dc


class ConfigManager:
    """Loads, saves, and provides access to TuposcanConfig."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._path = Path(config_path) if config_path else None
        self._config: TuposcanConfig = copy.deepcopy(DEFAULT_CONFIG)
        if self._path and self._path.exists():
            self.load()

    @property
    def config(self) -> TuposcanConfig:
        return self._config

    @config.setter
    def config(self, value: TuposcanConfig) -> None:
        self._config = value

    def load(self, path: str | Path | None = None) -> TuposcanConfig:
        p = Path(path) if path else self._path
        if not p or not p.exists():
            log.info("No config file at %s, using defaults", p)
            return self._config
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._config = copy.deepcopy(DEFAULT_CONFIG)
            merge_dataclass(self._config, data)
            log.info("Loaded config from %s", p)
        except Exception:
            log.exception("Failed to load config from %s, using defaults", p)
            self._config = copy.deepcopy(DEFAULT_CONFIG)
        return self._config

    def save(self, path: str | Path | None = None) -> None:
        p = Path(path) if path else self._path
        if not p:
            raise ValueError("No path specified for saving config")
        p.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self._config)
        p.write_text(json.dumps(data, indent=2, default=_enum_serialiser), encoding="utf-8")
        log.info("Saved config to %s", p)

    def snapshot(self) -> dict:
        """Return a serialisable dict copy (for config_snapshot.json)."""
        return json.loads(json.dumps(asdict(self._config), default=_enum_serialiser))
