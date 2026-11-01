"""
Structured logging setup for the SIP Discovery Engine.

Provides a consistent logger with timestamps, levels, and module names.
Log level is configurable via the LOG_LEVEL environment variable.
"""

from __future__ import annotations

import logging
import os
import sys


# Default log format: timestamp | level | module | message
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging(level: str | None = None) -> None:
    """
    Initialize the root logger with structured formatting.
    
    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to LOG_LEVEL env var, or INFO if not set.
    """
    global _initialized
    
    if _initialized:
        return
    
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    numeric_level = getattr(logging, level, logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger. Ensures logging is initialized first.
    
    Args:
        name: Logger name (typically __name__ of the calling module).
    
    Returns:
        Configured logging.Logger instance.
    
    Usage:
        from src.utils.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    setup_logging()
    return logging.getLogger(name)
