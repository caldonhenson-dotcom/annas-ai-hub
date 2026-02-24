"""
Circuit breaker pattern for external API calls.
Prevents cascading failures by temporarily blocking requests to failing services.

Usage:
    from scripts.lib.circuit_breaker import circuit_breaker_request

    # Simple usage — wraps request with circuit breaker
    response = circuit_breaker_request("hubspot", url, headers=headers)

    # Or use the breaker directly
    breaker = CircuitBreaker.get("monday", failure_threshold=5, reset_timeout=60)
    if breaker.can_execute():
        try:
            result = make_api_call()
            breaker.record_success()
        except Exception:
            breaker.record_failure()
"""
import time
from typing import Optional

import requests

from scripts.lib.logger import setup_logger
from scripts.lib.errors import CircuitOpenError

logger = setup_logger(__name__)


class CircuitBreaker:
    """
    Circuit breaker with three states: CLOSED, OPEN, HALF_OPEN.

    CLOSED: Requests pass through normally. Failures are counted.
    OPEN: Requests are blocked. After reset_timeout, moves to HALF_OPEN.
    HALF_OPEN: One test request allowed. Success closes, failure re-opens.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    _instances: dict = {}

    def __init__(self, service: str, failure_threshold: int = 5,
                 reset_timeout: int = 60):
        self.service = service
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0

    @classmethod
    def get(cls, service: str, **kwargs) -> "CircuitBreaker":
        """Get or create a circuit breaker for a service."""
        if service not in cls._instances:
            cls._instances[service] = cls(service, **kwargs)
        return cls._instances[service]

    @classmethod
    def reset_all(cls):
        """Reset all circuit breakers."""
        cls._instances.clear()

    def can_execute(self) -> bool:
        """Check if a request is allowed through the breaker."""
        if self.state == self.CLOSED:
            return True

        if self.state == self.OPEN:
            elapsed = time.time() - self.last_failure_time
            if elapsed >= self.reset_timeout:
                self.state = self.HALF_OPEN
                logger.info(
                    "Circuit half-open for '%s' — allowing test request",
                    self.service,
                )
                return True
            return False

        return True  # HALF_OPEN — allow one test request

    def record_success(self):
        """Record a successful request."""
        if self.state == self.HALF_OPEN:
            logger.info(
                "Circuit closed for '%s' — service recovered", self.service,
            )
        self.state = self.CLOSED
        self.failure_count = 0
        self.success_count += 1

    def record_failure(self):
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            logger.warning(
                "Circuit re-opened for '%s' — test request failed",
                self.service,
            )
        elif self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning(
                "Circuit opened for '%s' — %d consecutive failures "
                "(threshold: %d, reset in %ds)",
                self.service, self.failure_count,
                self.failure_threshold, self.reset_timeout,
            )

    @property
    def time_until_reset(self) -> float:
        """Seconds until the breaker resets (0 if not open)."""
        if self.state != self.OPEN:
            return 0.0
        elapsed = time.time() - self.last_failure_time
        return max(0.0, self.reset_timeout - elapsed)

    def status(self) -> dict:
        """Return breaker status as a dict."""
        return {
            "service": self.service,
            "state": self.state,
            "failures": self.failure_count,
            "threshold": self.failure_threshold,
            "time_until_reset": round(self.time_until_reset, 1),
        }


def circuit_breaker_request(
    service: str,
    url: str,
    method: str = "GET",
    timeout: int = 30,
    failure_threshold: int = 5,
    reset_timeout: int = 60,
    **kwargs,
) -> Optional[requests.Response]:
    """
    Make an HTTP request with circuit breaker protection.

    Args:
        service: Service name for the circuit breaker (e.g., "hubspot").
        url: URL to request.
        method: HTTP method.
        timeout: Request timeout in seconds.
        failure_threshold: Failures before opening circuit.
        reset_timeout: Seconds before retrying after circuit opens.
        **kwargs: Additional args for requests.

    Returns:
        Response object or None.

    Raises:
        CircuitOpenError: If the circuit is open.
    """
    breaker = CircuitBreaker.get(
        service,
        failure_threshold=failure_threshold,
        reset_timeout=reset_timeout,
    )

    if not breaker.can_execute():
        raise CircuitOpenError(
            service, breaker.failure_count, breaker.time_until_reset,
        )

    start = time.time()
    try:
        logger.debug("%s %s [circuit: %s]", method, url, breaker.state)
        response = requests.request(method, url, timeout=timeout, **kwargs)
        duration = time.time() - start

        if response.ok:
            breaker.record_success()
            logger.info(
                "%s %s — %d in %.2fs [circuit: %s]",
                method, url, response.status_code, duration, breaker.state,
            )
        else:
            breaker.record_failure()
            logger.warning(
                "%s %s — %d in %.2fs [circuit: %s]",
                method, url, response.status_code, duration, breaker.state,
            )
        return response

    except requests.exceptions.Timeout:
        breaker.record_failure()
        logger.error(
            "%s %s — TIMEOUT after %.2fs [circuit: %s]",
            method, url, time.time() - start, breaker.state,
        )
        return None

    except requests.exceptions.ConnectionError as e:
        breaker.record_failure()
        logger.error(
            "%s %s — CONNECTION_ERROR: %s [circuit: %s]",
            method, url, e, breaker.state,
        )
        return None

    except requests.RequestException as e:
        breaker.record_failure()
        logger.error(
            "%s %s — ERROR: %s [circuit: %s]",
            method, url, e, breaker.state,
        )
        return None
