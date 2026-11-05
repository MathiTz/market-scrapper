"""The identity the publisher and the warehouse must agree on.

``market.db``'s ``products.id`` is local to one machine and collides across rebuilds, so both sides
key a product by something stable: its barcode when the chain gave a real one, otherwise a hash of
its identity tokens and size.

It lives in its own module because the two sides need the same answer and neither can import the
other: ``warehouse.etl`` already imports ``services.public_api``, and ``public_api`` imports this.

``warehouse.etl`` re-exports both names, so its callers and tests keep working unchanged.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from services.public_api import match_tokens, parse_size


def normalize_gtin(gtin: Optional[str]) -> Optional[str]:
    """14-digit EAN, or None when the value is missing, malformed or an internal PLU."""
    digits = re.sub(r"\D", "", gtin or "")
    if len(digits) not in (8, 12, 13, 14):
        return None
    if len(digits) == 13 and digits.startswith("2"):  # GS1 variable-measure prefix
        return None
    return digits.zfill(14)


def canonical_key(product: dict) -> str:
    """``gtin:<ean>`` when the product has a real barcode, else ``tok:<hash of tokens + size>``."""
    gtin = normalize_gtin(product.get("gtin"))
    if gtin:
        return f"gtin:{gtin}"
    tokens = sorted(match_tokens(product["name"]))
    amount, unit, pack = parse_size(product["name"])
    material = "|".join(tokens) + f"|{amount}{unit}x{pack}"
    return "tok:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
