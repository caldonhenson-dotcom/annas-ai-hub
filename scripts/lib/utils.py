"""
Utility functions for Annas AI Hub.
Atomic file writes, retry logic, HTTP helpers, and caching.

Usage:
    from scripts.lib.utils import atomic_write_json, safe_request, retry_on_exception
"""
import json
import os
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

from scripts.lib.logger import setup_logger

logger = setup_logger(__name__)


def atomic_write_json(data: Dict, file_path: str | Path, indent: int = 2) -> bool:
    """
    Write JSON data to file atomically using temp file + rename.
    Prevents data corruption if the program crashes during write.

    Args:
        data: Dictionary to serialize as JSON.
        file_path: Target file path.
        indent: JSON indentation level.

    Returns:
        True if successful, False otherwise.
    """
    file_path = Path(file_path)
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, default=str)

        os.replace(temp_path, file_path)
        logger.debug("Atomically wrote JSON to %s", file_path)
        return True

    except Exception as e:
        logger.error("Failed to write JSON to %s: %s", file_path, e)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        return False


def retry_on_exception(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator that retries a function on specified exceptions.

    Args:
        max_attempts: Maximum number of attempts.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier for delay after each retry.
        exceptions: Tuple of exception types to catch.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts, e, exc_info=True,
                        )
                        raise
                    logger.warning(
                        "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        func.__name__, attempt, max_attempts, e, current_delay,
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator


def safe_request(
    url: str,
    method: str = "GET",
    timeout: int = 30,
    max_retries: int = 3,
    **kwargs,
) -> Optional[requests.Response]:
    """
    Make HTTP request with automatic retries and error handling.

    Args:
        url: URL to request.
        method: HTTP method.
        timeout: Request timeout in seconds.
        max_retries: Maximum retry attempts.
        **kwargs: Additional arguments passed to requests.

    Returns:
        Response object if successful, None if all retries failed.
    """
    @retry_on_exception(
        max_attempts=max_retries,
        delay=1.0,
        exceptions=(
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ),
    )
    def _make_request():
        start = time.time()
        logger.debug("%s %s", method, url)
        response = requests.request(method, url, timeout=timeout, **kwargs)
        duration = time.time() - start
        logger.info(
            "%s %s — %d in %.2fs", method, url, response.status_code, duration,
        )
        response.raise_for_status()
        return response

    try:
        return _make_request()
    except requests.RequestException as e:
        logger.error("Request failed after retries: %s %s - %s", method, url, e)
        return None


def fetch_with_cache(
    url: str,
    cache_path: str | Path,
    max_age_hours: float = 24,
    headers: dict = None,
    params: dict = None,
) -> Optional[Dict]:
    """
    Fetch URL with file-based caching.
    Returns cached data if fresh, otherwise fetches and caches.
    Falls back to stale cache if fetch fails.
    """
    cache_path = Path(cache_path)

    if cache_path.exists():
        cache_age = time.time() - cache_path.stat().st_mtime
        if cache_age < max_age_hours * 3600:
            logger.info("Cache hit: %s (age: %.1fh)", cache_path, cache_age / 3600)
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        logger.info(
            "Cache stale: %s (age: %.1fh, max: %.0fh)",
            cache_path, cache_age / 3600, max_age_hours,
        )

    logger.info("Fetching: %s", url)
    response = safe_request(url, headers=headers, params=params)
    if response and response.ok:
        data = response.json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(data, cache_path)
        logger.info("Cached: %s", cache_path)
        return data

    # Fall back to stale cache
    if cache_path.exists():
        logger.warning("Fetch failed, using stale cache: %s", cache_path)
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    logger.error("Fetch failed and no cache available: %s", url)
    return None


def ensure_directory(path: str | Path) -> Path:
    """Ensure directory exists, create if needed."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
