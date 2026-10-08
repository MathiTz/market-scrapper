from __future__ import annotations

import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import requests

from .consensus import consensus_merge
from .parser import CROP_PROMPT, parse_reply_json
from .schemas import (
    NOT_RETRYABLE,
    AuthenticationError,
    BadReplyError,
    BadRequestError,
    Flags,
    Item,
    ModelNotFoundError,
    ProviderUnavailableError,
    QuotaError,
    RateLimitedError,
    Receipt,
    ReceiptOcrError,
    Timings,
)
from .tiler import make_tiles
from .validator import validate_items

logger = logging.getLogger("receiptocr")

__all__ = [
    "ReceiptExtractor",
    "Receipt",
    "Item",
    "Flags",
    "Timings",
    "ReceiptOcrError",
    "AuthenticationError",
    "QuotaError",
    "RateLimitedError",
    "ProviderUnavailableError",
    "BadReplyError",
    "ModelNotFoundError",
    "BadRequestError",
]


BAD_REQUEST_STATUSES = frozenset({400, 413, 422})


def _safe_retry_after(value) -> float | None:
    """Parse a retry-after header; None when absent or non-numeric
    (HTTP-date formats are deliberately ignored — we cap sleeps anyway)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify(exc: Exception) -> ReceiptOcrError:
    """Map a raw exception from the provider call to a typed error."""
    if isinstance(exc, ReceiptOcrError):
        return exc
    status = None
    retry_after = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        status = resp.status_code
        headers = getattr(resp, "headers", None)
        retry_after = _safe_retry_after(headers.get("retry-after")) if headers else None
    if status in (401, 403):
        return AuthenticationError(f"provider rejected credentials (HTTP {status})")
    if status == 402:
        return QuotaError("provider account out of credits or over quota (HTTP 402)")
    if status == 404:
        return ModelNotFoundError("unknown model tag (HTTP 404)")
    if status in BAD_REQUEST_STATUSES:
        return BadRequestError(f"provider rejected request (HTTP {status}): "
                               "check model_tag and image payload")
    if status == 429:
        msg = "provider rate limit (HTTP 429)"
        if retry_after is not None:
            msg += f", retry-after={retry_after:g}s"
        err = RateLimitedError(msg)
        err.retry_after = retry_after
        return err
    if status is not None and status >= 500:
        return ProviderUnavailableError(f"provider error (HTTP {status})")
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return ProviderUnavailableError(f"provider unreachable: {type(exc).__name__}")
    return ProviderUnavailableError(f"{type(exc).__name__}: {exc}")


@dataclass
class ReceiptExtractor:
    """Extracts items and metadata from Brazilian NFC-e receipts using overlapping zoomed tiles."""

    model_tag: str = "gemma4:cloud"
    n_tiles: int = 3
    tile_overlap: float = 0.10
    tile_zoom: float = 2.0
    tile_jobs: int = 3
    api_key: str | None = None
    timeout: float = 60.0

    def _read_tile(
        self, tile: np.ndarray, api_key: str
    ) -> list[Item]:
        h, w = tile.shape[:2]
        if max(h, w) > 2000:
            f = 2000 / max(h, w)
            tile = cv2.resize(tile, (int(w * f), int(h * f)),
                              interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise ProviderUnavailableError("Failed to encode tile image to JPEG")
        b64 = base64.b64encode(buf).decode()

        payload = {
            "model": self.model_tag,
            "messages": [
                {
                    "role": "user",
                    "content": CROP_PROMPT,
                    "images": [b64],
                }
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            resp = requests.post(
                "https://ollama.com/api/chat",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise _classify(exc) from exc
        try:
            body = resp.json()
            reply = body.get("message", {}).get("content", "") \
                if isinstance(body, dict) else ""
        except ValueError as exc:
            raise BadReplyError(f"provider returned non-JSON body: {exc}") from exc
        try:
            return parse_reply_json(reply)
        except ReceiptOcrError as exc:
            raise BadReplyError(str(exc)) from exc

    def _fetch_tile_with_retry(
        self, idx: int, tile: np.ndarray, api_key: str
    ) -> tuple[int, list[Item] | None]:
        last: ReceiptOcrError | None = None
        for attempt in range(2):
            try:
                items = self._read_tile(tile, api_key)
                return idx, items
            except ReceiptOcrError as exc:
                last = exc
                if isinstance(exc, NOT_RETRYABLE):
                    raise
                logger.warning(
                    "Tile %d failed on attempt %d: %s", idx, attempt + 1, exc
                )
                if attempt == 0:
                    backoff = getattr(exc, "retry_after", None) or 2.0
                    time.sleep(min(backoff, 30.0))
        return idx, None

    def extract(self, image_path: str | Path) -> Receipt:
        """Extract items and validation flags from a receipt image."""
        api_key = self.api_key or os.environ.get("OLLAMA_API_KEY")
        if not api_key:
            env_path = Path(".env")
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("OLLAMA_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            api_key = val
                            break
        if not api_key:
            raise ReceiptOcrError(
                "Missing Ollama API key. Provide api_key or set OLLAMA_API_KEY environment variable."
            )

        img = cv2.imread(str(image_path))
        if img is None:
            raise ReceiptOcrError(f"Unreadable image: {image_path}")

        t_start = time.perf_counter()

        t_slice = time.perf_counter()
        tiles = make_tiles(
            img,
            n_tiles=self.n_tiles,
            overlap=self.tile_overlap,
            zoom=self.tile_zoom,
        )
        slice_ms = (time.perf_counter() - t_slice) * 1000

        t_ocr = time.perf_counter()
        results: list[list[Item] | None] = [None] * len(tiles)
        max_workers = max(1, min(self.tile_jobs, len(tiles)))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        futures = [
            executor.submit(self._fetch_tile_with_retry, i, tile, api_key)
            for i, tile in enumerate(tiles)
        ]
        try:
            for f in futures:
                try:
                    idx, items = f.result()
                except ReceiptOcrError:
                    # non-retryable (auth/quota/model/bad-request) aborts
                    # the extraction; do not wait for the remaining tiles
                    raise
                except Exception as exc:
                    logger.warning("Tile crashed unexpectedly: %s", exc)
                    continue
                results[idx] = items
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        ocr_ms = (time.perf_counter() - t_ocr) * 1000

        successful = [
            (i, items)
            for i, items in enumerate(results)
            if items is not None
        ]
        if not successful:
            raise ReceiptOcrError(
                "All tiles failed extraction after retry attempts."
            )
        failed_tiles = [i for i, items in enumerate(results) if items is None]

        t_merge = time.perf_counter()
        raw = [
            {"tile": i, "items": [asdict(item) for item in items]}
            for i, items in successful
        ]
        readings = [items for _, items in successful]
        merged_items, _ = consensus_merge(readings)
        flags = validate_items(merged_items)
        merge_ms = (time.perf_counter() - t_merge) * 1000

        total_ms = (time.perf_counter() - t_start) * 1000
        timings = Timings(
            slice_ms=round(slice_ms, 2),
            ocr_ms=round(ocr_ms, 2),
            merge_ms=round(merge_ms, 2),
            total_ms=round(total_ms, 2),
        )

        return Receipt(
            items=merged_items,
            flags=flags,
            timings=timings,
            raw=raw,
            failed_tiles=failed_tiles,
        )
