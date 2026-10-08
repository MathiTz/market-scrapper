from __future__ import annotations

import argparse
import sys

from . import ReceiptExtractor
from .schemas import (
    AuthenticationError,
    BadReplyError,
    ModelNotFoundError,
    ProviderUnavailableError,
    QuotaError,
    RateLimitedError,
    ReceiptOcrError,
)

EXIT_USAGE = 1
EXIT_AUTH = 3
EXIT_PROVIDER = 4


def _exit_code(exc: ReceiptOcrError) -> int:
    if isinstance(exc, (AuthenticationError, QuotaError)):
        return EXIT_AUTH
    if isinstance(exc, (ProviderUnavailableError, RateLimitedError, BadReplyError,
                        ModelNotFoundError)):
        return EXIT_PROVIDER
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Extract item lines from Brazilian NFC-e receipts."
    )
    parser.add_argument("image", help="Path to receipt image file.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw receipt JSON to stdout.",
    )
    args = parser.parse_args(argv)

    extractor = ReceiptExtractor()
    try:
        receipt = extractor.extract(args.image)
    except ReceiptOcrError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        sys.exit(_exit_code(exc))

    if args.json:
        sys.stdout.write(receipt.to_json() + "\n")
    else:
        print(
            f"{'LINE':<5} {'NAME':<35} {'QTY':>6} {'UNIT':<5} {'PRICE':>8} {'DISC':>8} {'TOTAL':>8}"
        )
        print("-" * 80)
        for it in receipt.items:
            line_str = f"{it.line_no:03d}" if it.line_no is not None else "---"
            name_str = (
                (it.name[:32] + "...") if len(it.name) > 35 else it.name
            )
            qty_str = f"{it.qty:.2f}" if it.qty is not None else ""
            unit_str = it.unit or ""
            up_str = f"{it.unit_price:.2f}" if it.unit_price is not None else ""
            disc_str = f"{it.discount:.2f}" if it.discount is not None else ""
            tot_str = f"{it.total:.2f}" if it.total is not None else ""
            print(
                f"{line_str:<5} {name_str:<35} {qty_str:>6} {unit_str:<5} {up_str:>8} {disc_str:>8} {tot_str:>8}"
            )
        print("-" * 80)
        status = (
            "ok"
            if receipt.flags.ok
            else f"bad_math={receipt.flags.bad_math}, missing={receipt.flags.missing_lines}, dup={receipt.flags.duplicate_lines}"
        )
        print(f"Items: {len(receipt.items)} | Flags: {status}"
              + (f" | FAILED TILES: {receipt.failed_tiles}" if receipt.degraded else ""))

    sys.stderr.write(
        f"Timings: slice={receipt.timings.slice_ms:.1f}ms "
        f"ocr={receipt.timings.ocr_ms:.1f}ms "
        f"merge={receipt.timings.merge_ms:.1f}ms "
        f"total={receipt.timings.total_ms:.1f}ms\n"
    )
