"""
Centralized logging for Annas AI Hub.
Provides consistent logging across all modules with console + daily file output.

Usage:
    from scripts.lib.logger import setup_logger
    logger = setup_logger(__name__)
    logger.info("Processing started")
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# Project root — Annas Ai Hub/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"


def setup_logger(
    name: str,
    level: str = "INFO",
    log_to_file: bool = True,
    log_dir: Path = None,
) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name (typically __name__ from calling module).
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_to_file: Whether to also log to a file.
        log_dir: Directory for log files (default: project_root/logs).

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    if log_to_file:
        target_dir = Path(log_dir) if log_dir else LOG_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        log_file = target_dir / f"{datetime.now().strftime('%Y%m%d')}_annas_hub.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get an existing logger or create one with default settings."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
