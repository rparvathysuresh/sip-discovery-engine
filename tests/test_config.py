"""
Tests for configuration utilities in src/utils/config.py.
"""

import os
import pytest
from pathlib import Path

from src.utils.config import (
    ConfigError,
    _resolve_env_vars,
    get_config,
    get_extraction_config,
    get_scoring_config,
    get_source_config,
)


def test_resolve_env_vars_with_existing_var(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "secret_value")
    res = _resolve_env_vars("Bearer ${TEST_KEY}")
    assert res == "Bearer secret_value"


def test_resolve_env_vars_with_default():
    res = _resolve_env_vars("${NON_EXISTENT_VAR:-default_val}")
    assert res == "default_val"


def test_resolve_env_vars_missing_raises_error():
    with pytest.raises(ConfigError):
        _resolve_env_vars("${COMPLETELY_UNSET_ENV_VAR_XYZ}")


def test_get_config():
    config = get_config(reload=True)
    assert "sources" in config
    assert "extraction" in config
    assert "scoring" in config
    assert "guardrails" in config
    assert "database" in config
    assert "chromadb" in config


def test_get_source_config():
    reddit_cfg = get_source_config("reddit")
    assert "subreddits" in reddit_cfg
    assert "IndiaInvestments" in reddit_cfg["subreddits"]

    with pytest.raises(ConfigError):
        get_source_config("unsupported_source_xyz")


def test_get_extraction_config():
    ext_cfg = get_extraction_config()
    assert "models" in ext_cfg
    assert ext_cfg["models"]["primary"] == "openai/gpt-oss-120b"


def test_get_scoring_config():
    scoring_cfg = get_scoring_config()
    assert "weights" in scoring_cfg
    assert scoring_cfg["weights"]["frequency"] == 0.4

