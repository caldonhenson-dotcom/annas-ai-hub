"""
Custom error classes for Annas AI Hub.
Structured error handling with error codes across all modules.

Hierarchy:
    HubError
    ├── APIError
    │   ├── APITimeoutError
    │   ├── APIRateLimitError
    │   ├── APIAuthError
    │   ├── CircuitOpenError
    │   └── VoyagerAPIError
    │       ├── VoyagerAuthError
    │       └── VoyagerRateLimitError
    ├── DataError
    │   ├── ConfigError
    │   ├── SchemaValidationError
    │   └── DataFetchError
    ├── PipelineError
    │   ├── PipelineStepError
    │   └── QuotaExceededError
    └── OutreachError
"""


class HubError(Exception):
    """Base exception for all Annas AI Hub errors."""

    def __init__(self, message: str, code: str = "UNKNOWN", details: dict = None):
        self.code = code
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


# --- API Errors ---

class APIError(HubError):
    """Base class for external API errors."""

    def __init__(self, message: str, code: str = "API_ERROR",
                 status_code: int = None, url: str = None, **kwargs):
        self.status_code = status_code
        self.url = url
        details = {"status_code": status_code, "url": url, **kwargs}
        super().__init__(message, code=code, details=details)


class APITimeoutError(APIError):
    """Request timed out."""

    def __init__(self, url: str, timeout: int):
        super().__init__(
            f"Request timed out after {timeout}s: {url}",
            code="API_TIMEOUT", url=url, timeout=timeout,
        )


class APIRateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(self, url: str, retry_after: int = None):
        msg = f"Rate limit exceeded: {url}"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(
            msg, code="API_RATE_LIMIT", url=url, retry_after=retry_after,
        )


class APIAuthError(APIError):
    """Authentication or authorization failure."""

    def __init__(self, url: str, status_code: int = 401):
        super().__init__(
            f"Authentication failed: {url}",
            code="API_AUTH_FAILED", url=url, status_code=status_code,
        )


class CircuitOpenError(APIError):
    """Circuit breaker is open — requests blocked."""

    def __init__(self, service: str, failures: int, reset_time: float):
        super().__init__(
            f"Circuit open for '{service}' after {failures} failures. "
            f"Resets in {reset_time:.0f}s.",
            code="CIRCUIT_OPEN", service=service,
        )


# --- Data Errors ---

class DataError(HubError):
    """Base class for data processing errors."""
    pass


class ConfigError(DataError):
    """Configuration file error."""

    def __init__(self, message: str, config_path: str = None):
        super().__init__(
            message, code="CONFIG_ERROR",
            details={"config_path": config_path},
        )


class SchemaValidationError(DataError):
    """Data doesn't match expected schema."""

    def __init__(self, message: str, field: str = None):
        super().__init__(
            message, code="SCHEMA_INVALID", details={"field": field},
        )


class DataFetchError(DataError):
    """Failed to fetch or load data from storage."""

    def __init__(self, message: str, source: str = None):
        super().__init__(
            message, code="DATA_FETCH_FAILED", details={"source": source},
        )


# --- Pipeline Errors ---

class PipelineError(HubError):
    """Pipeline orchestration error."""
    pass


class PipelineStepError(PipelineError):
    """A specific pipeline step failed."""

    def __init__(self, step_name: str, cause: Exception = None):
        msg = f"Pipeline step '{step_name}' failed"
        if cause:
            msg += f": {cause}"
        super().__init__(
            msg, code="PIPELINE_STEP_FAILED", details={"step": step_name},
        )


class QuotaExceededError(PipelineError):
    """API quota exceeded."""

    def __init__(self, service: str, used: int, limit: int):
        super().__init__(
            f"{service} quota exceeded: {used}/{limit}",
            code="QUOTA_EXCEEDED",
            details={"service": service, "used": used, "limit": limit},
        )


# --- Voyager / LinkedIn Errors ---

class VoyagerAPIError(APIError):
    """LinkedIn Voyager API error."""

    def __init__(self, message: str, status_code: int = None):
        super().__init__(
            message, code="VOYAGER_ERROR", status_code=status_code,
            url="linkedin.com/voyager",
        )


class VoyagerAuthError(VoyagerAPIError):
    """LinkedIn session expired or invalid."""

    def __init__(self, message: str = "LinkedIn session expired"):
        super().__init__(message, status_code=401)
        self.code = "VOYAGER_AUTH_FAILED"


class VoyagerRateLimitError(VoyagerAPIError):
    """LinkedIn rate limit hit."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"LinkedIn rate limit exceeded (retry after {retry_after}s)",
            status_code=429,
        )
        self.code = "VOYAGER_RATE_LIMIT"
        self.details["retry_after"] = retry_after


# --- Outreach Errors ---

class OutreachError(HubError):
    """Base class for outreach engine errors."""

    def __init__(self, message: str, code: str = "OUTREACH_ERROR", **kwargs):
        super().__init__(message, code=code, details=kwargs)
