"""
Test configuration and fixtures for the SIP Discovery Engine.
"""

import os
import tempfile
from pathlib import Path
import pytest

from src.db.connection import init_db


@pytest.fixture
def temp_db_path(tmp_path):
    """Provides a temporary SQLite database file path."""
    db_file = tmp_path / "test_sip.db"
    return str(db_file)


@pytest.fixture
def test_db(temp_db_path):
    """Provides an initialized SQLite database connection that is closed after test."""
    conn = init_db(temp_db_path)
    yield conn
    conn.close()

