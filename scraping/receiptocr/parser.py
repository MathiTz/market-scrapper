from __future__ import annotations

import json
import re

from .schemas import Item, ReceiptOcrError

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
LINE_RE = re.compile(r"^0*(\d{1,3})(?:\s+printed_total=.*)?$")

CROP_PROMPT = """You are an OCR transcription engine for Brazilian NFC-e supermarket
receipts. This image is a ZOOMED CROP of a few item lines from one receipt
(single column, possibly cut mid-line at top/bottom edges).

Transcribe ONLY complete item lines you can see. Return ONLY a JSON object,
no markdown, with this exact shape:

{
  "items": [
    {
      "line": string,          // item number printed at the left, e.g. "007"; "" if unreadable
      "code": string,          // the product code / barcode printed on the line ("Código"), digits only; "" if not shown
      "name": string,          // product name as printed (uppercase abbreviations as-is)
      "qty": number,           // quantity (un) or weight (kg); 1 if not shown
      "unit": "un"|"unid"|"kg"|null,
      "unit_price": number,    // price right after "x"; 7,60 -> 7.60
      "discount": number|null, // value on the "Desconto" line for this item, as printed
      "printed_total": number  // the rightmost total for this line, transcribed as-is
    }
  ]
}

Rules:
- TRANSCRIBE ONLY: copy the digits literally; do NOT calculate or correct.
- The code is the long number (usually 13 digits) printed on the line, next to the name; copy every digit.
  A short internal number (under 8 digits) is not a barcode: leave code "".
- Ignore partial/cut lines at the very top or bottom of the crop.
- Ignore any line that is clearly a subtotal/tax/payment line.
Return JSON only."""


def clean_code(value: object) -> str | None:
    """A barcode (EAN-8, UPC-A, EAN-13 or GTIN-14) from what the model transcribed, or None.

    Digits only, and the GS1 check digit must hold: a single misread digit fails it, and no code is better
    than a code that names another product.
    """
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) not in (8, 12, 13, 14) or set(digits) == {"0"}:
        return None
    body, check = digits[:-1], int(digits[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return digits if (10 - total % 10) % 10 == check else None


MIN_READ_DIGITS, MAX_READ_DIGITS = 8, 16


def code_read(value: object) -> list[str]:
    """The digits the model transcribed as a barcode when they could be one (8-16 digits, not all zeros), else [].
    Not checked: this is what `clean_code` rejects too, kept so a one-digit slip can be repaired by a caller."""
    digits = re.sub(r"\D", "", str(value or ""))
    return [digits] if MIN_READ_DIGITS <= len(digits) <= MAX_READ_DIGITS and set(digits) != {"0"} else []


def parse_reply_json(text: str) -> list[Item]:
    m = JSON_RE.search(text)
    if not m:
        raise ReceiptOcrError(f"no JSON in reply: {text[:200]}")
    data = json.loads(m.group(0))
    items_raw = data.get("items", [])
    items: list[Item] = []

    for it in items_raw:
        raw_line = it.get("line")
        line_no = None
        if raw_line is not None:
            line_str = str(raw_line).strip()
            m_line = LINE_RE.match(line_str)
            if m_line:
                line_no = int(m_line.group(1))
            elif line_str.isdigit():
                line_no = int(line_str)

        name = str(it.get("name") or "")
        code = clean_code(it.get("code"))
        qty = float(it["qty"]) if it.get("qty") is not None else None
        unit = str(it["unit"]) if it.get("unit") is not None else None
        unit_price = float(it["unit_price"]) if it.get("unit_price") is not None else None
        discount = abs(float(it["discount"])) if it.get("discount") is not None else None
        printed_total = float(it["printed_total"]) if it.get("printed_total") is not None else None

        if printed_total is not None:
            total = printed_total
        elif unit_price is not None:
            q = qty if qty is not None else 1.0
            d = discount or 0.0
            total = round(q * unit_price - d, 2)
        else:
            total = None

        items.append(
            Item(
                line_no=line_no,
                name=name,
                code=code,
                code_reads=code_read(it.get("code")),
                qty=qty,
                unit=unit,
                unit_price=unit_price,
                discount=discount,
                total=total,
                printed_total=printed_total,
                contested=False,
            )
        )

    return items
