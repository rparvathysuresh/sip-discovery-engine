"""
Configuration loader for the SIP Discovery Engine.

Loads YAML config files from the config/ directory and resolves
environment variable references (${VAR_NAME} syntax).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Project root — two levels up from this file (src/utils/config.py → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

# Cache for loaded configs
_config_cache: Optional[dict[str, Any]] = None


def _resolve_env_vars(value: Any) -> Any:
    """
    Recursively resolve ${VAR_NAME} or ${VAR_NAME:-default} references in config values.
    
    If the env var is not set and no default is provided, raises a ConfigError.
    """
    if isinstance(value, str):
        pattern = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")
        for match in pattern.finditer(value):
            full_match = match.group(0)
            var_name = match.group(1)
            default_val = match.group(2)
            env_value = os.getenv(var_name)
            if env_value is None:
                if default_val is not None:
                    env_value = default_val
                else:
                    raise ConfigError(
                        f"Environment variable '{var_name}' is referenced in config "
                        f"but not set. Add it to your .env file or set it in your environment."
                    )
            value = value.replace(full_match, env_value)
        return value
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


def load_yaml(file_path: Path) -> dict[str, Any]:
    """
    Load a single YAML file and resolve environment variable references.
    
    Args:
        file_path: Path to the YAML file.
    
    Returns:
        Parsed and resolved config dictionary.
    
    Raises:
        ConfigError: If file doesn't exist or YAML is invalid.
    """
    if not file_path.exists():
        raise ConfigError(f"Config file not found: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {file_path}: {e}")
    
    return _resolve_env_vars(raw)


def get_config(reload: bool = False) -> dict[str, Any]:
    """
    Load and merge all config files from config/ directory.
    
    Merges: sources.yaml, extraction.yaml, scoring.yaml, guardrails.yaml
    into a single config dict keyed by filename (without extension).
    
    Results are cached; pass reload=True to force a refresh.
    
    Returns:
        Merged config dict, e.g.:
        {
            "sources": {...},
            "extraction": {...},
            "scoring": {...},
            "guardrails": {...},
            "database": {"path": "data/sip_discovery.db"},
        }
    """
    global _config_cache
    
    if _config_cache is not None and not reload:
        return _config_cache
    
    config: dict[str, Any] = {}
    
    # Load each config file if it exists
    config_files = ["sources", "extraction", "scoring", "guardrails"]
    for name in config_files:
        file_path = CONFIG_DIR / f"{name}.yaml"
        if file_path.exists():
            config[name] = load_yaml(file_path)
    
    # Add database config from env
    config["database"] = {
        "path": os.getenv("DATABASE_PATH", "data/sip_discovery.db"),
    }
    
    # Add ChromaDB config from env
    config["chromadb"] = {
        "path": os.getenv("CHROMADB_PATH", "data/chromadb"),
    }
    
    _config_cache = config
    return config


def get_source_config(source_name: str) -> dict[str, Any]:
    """
    Get configuration for a specific source connector.
    
    Args:
        source_name: e.g. "reddit", "youtube", "playstore"
    
    Returns:
        Config dict for that source.
    
    Raises:
        ConfigError: If source config is not found.
    """
    config = get_config()
    sources = config.get("sources", {})
    if source_name not in sources:
        raise ConfigError(
            f"No configuration found for source '{source_name}'. "
            f"Available sources: {list(sources.keys())}"
        )
    return sources[source_name]


def get_extraction_config() -> dict[str, Any]:
    """Get the extraction (LLM) configuration."""
    config = get_config()
    return config.get("extraction", {})


def get_scoring_config() -> dict[str, Any]:
    """Get the opportunity scoring configuration."""
    config = get_config()
    return config.get("scoring", {})
