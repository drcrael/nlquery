"""Credential-free configuration files and validated environment overrides."""

import json
import os
from pathlib import Path

from pydantic import Field

from nlquery.core.models import DiscoveryConfig, Model, QueryPolicy, SemanticCatalog
from nlquery.exceptions import ConfigurationError
from nlquery.guardrails.secrets import ensure_safe


class QueryConfig(Model):
    policy: QueryPolicy = Field(default_factory=QueryPolicy)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "QueryConfig":
        try:
            data = json.loads(Path(path).read_text()) if path else {}
            ensure_safe(data)
            if "NLQUERY_MAX_ROWS" in os.environ:
                data.setdefault("policy", {})["max_rows"] = int(os.environ["NLQUERY_MAX_ROWS"])
            return cls.model_validate(data)
        except Exception:
            raise ConfigurationError("Invalid credential-free NLQuery configuration") from None


def load_catalog(path: str | Path) -> SemanticCatalog:
    try:
        text = Path(path).read_text()
        if str(path).endswith((".yaml", ".yml")):
            import yaml

            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        ensure_safe(data)
        return SemanticCatalog.model_validate(data)
    except Exception:
        raise ConfigurationError("Invalid semantic catalog or missing nlquery[yaml]") from None
