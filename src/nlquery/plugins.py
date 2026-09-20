"""Explicit plugin loading. Installed plugins execute trusted local Python code."""

from importlib.metadata import entry_points
from typing import Any

from nlquery.exceptions import ConfigurationError


def load_connector(name: str, **kwargs: Any) -> Any:
    matches = list(entry_points(group="nlquery.connectors", name=name))
    if len(matches) != 1:
        raise ConfigurationError("Connector plugin is missing or ambiguous")
    return matches[0].load()(**kwargs)
