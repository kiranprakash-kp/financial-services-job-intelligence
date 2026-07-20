"""Typed exceptions.

The split between retryable and non-retryable errors drives both the HTTP retry
layer and Temporal's non-retryable exception configuration. Keep these classes
stable — Temporal references them by name.
"""

from __future__ import annotations


class JobIntelError(Exception):
    """Base class for all application errors."""


class RetryableError(JobIntelError):
    """Transient failures worth retrying (network blips, 5xx, 429)."""


class TransientSourceError(RetryableError):
    """A source returned a transient error (timeout, 5xx, connection reset)."""


class RateLimitedError(RetryableError):
    """HTTP 429. Carries the server's Retry-After hint when present."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class NonRetryableError(JobIntelError):
    """Failures where retrying cannot help; surfaced to the run error report."""


class AccessDeniedError(NonRetryableError):
    """WAF challenge, CAPTCHA, or explicit block. Stop and report — never evade."""


class ParsingError(NonRetryableError):
    """Response shape did not match expectations (schema drift)."""


class ValidationError(NonRetryableError):
    """A record failed domain validation (e.g. no valid US location)."""


class ConfigurationError(NonRetryableError):
    """Missing or invalid configuration."""


class DatabaseError(NonRetryableError):
    """Persistence-layer failure."""


class DisallowedDomainError(NonRetryableError):
    """A request or redirect targeted a domain outside the company allowlist."""
