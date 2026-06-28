"""Load and save :class:`BacktestConfig` to YAML or JSON.

Lets users version-control reproducible experiment definitions and lets the web
UI save / reload configurations.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from dcatoolbox.config.settings import BacktestConfig

__all__ = ["save_config", "load_config"]


def save_config(config: BacktestConfig, path: Path | str) -> Path:
    """Serialise ``config`` to ``path`` (``.yaml``/``.yml`` or ``.json``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    if path.suffix.lower() in {".yaml", ".yml"}:
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_config(path: Path | str) -> BacktestConfig:
    """Load a :class:`BacktestConfig` from a YAML or JSON file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    return BacktestConfig.model_validate(payload)
