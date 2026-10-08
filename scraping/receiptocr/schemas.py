from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


class ReceiptOcrError(Exception):
    """Base exception for Receipt OCR extraction errors."""


class AuthenticationError(ReceiptOcrError):
    """Provider rejected the credentials (HTTP 401/403). Not retryable."""


class QuotaError(ReceiptOcrError):
    """Account out of credits or over quota (HTTP 402). Not retryable."""


class RateLimitedError(ReceiptOcrError):
    """Provider rate-limited the request (HTTP 429). Retryable with backoff."""


class ProviderUnavailableError(ReceiptOcrError):
    """Provider unreachable or failing (5xx, connection, DNS, TLS). Retryable."""


class BadReplyError(ReceiptOcrError):
    """HTTP 200 but the reply is empty or not parseable JSON. Retryable once."""


class ModelNotFoundError(ReceiptOcrError):
    """Unknown model tag (HTTP 404). Not retryable."""


class BadRequestError(ReceiptOcrError):
    """Provider rejected the request shape (HTTP 400/413/422).
    Retrying the identical payload is pointless. Not retryable."""


# Retry policy per error class: non-retryable ones abort immediately.
NOT_RETRYABLE = (AuthenticationError, QuotaError, ModelNotFoundError,
                 BadRequestError)


@dataclass
class Item:
    """Single item extracted from a receipt."""

    line_no: int | None = None
    name: str = ""
    qty: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    discount: float | None = None
    total: float | None = None
    printed_total: float | None = None
    contested: bool = False


@dataclass
class Flags:
    """Deterministic structural validation flags."""

    bad_math: list[int] = field(default_factory=list)
    missing_lines: list[int] = field(default_factory=list)
    duplicate_lines: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.bad_math or self.missing_lines or self.duplicate_lines)


@dataclass
class Timings:
    """Execution timing measurements in milliseconds."""

    slice_ms: float = 0.0
    ocr_ms: float = 0.0
    merge_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class Receipt:
    """Complete extracted receipt document."""

    items: list[Item] = field(default_factory=list)
    flags: Flags = field(default_factory=Flags)
    timings: Timings = field(default_factory=Timings)
    raw: list[dict] = field(default_factory=list)
    failed_tiles: list[int] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        """True when at least one tile failed — result quality may be reduced."""
        return bool(self.failed_tiles)

    def to_json(self) -> str:
        """Serialize receipt to formatted JSON string."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
