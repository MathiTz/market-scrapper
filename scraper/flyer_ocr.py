"""Read product offers from flyer images with EasyOCR (optional dependency).

Cometa's flyers are flat images, so prices have to come from OCR, and OCR of
stylised price tags is not trustworthy on its own: on real flyers EasyOCR
turned 19,99 into 19,29 with 0.9 confidence, and re-reading the same crop gave
the same wrong answer, so agreement between two reads proves nothing.

What we can check independently is the discount badge some flyers print next
to each product ("23% DE DESCONTO", "De: 6,49", "Por: 4,99"). An offer is
only accepted when the badge percentage matches the two OCR'd prices:

    round((1 - por / de) * 100) == badge

A gross misread (dropped digit, 9 read as 2, lost leading "1") breaks that
equation and the offer is dropped. It cannot catch a one-cent slip on an
expensive item, and flyers without badges (price tags only) yield nothing.
Precision is preferred over recall: a wrong price could win a cheapest-store
comparison, a missing one only costs an offer.

``easyocr`` is optional: :func:`ocr_available` says whether it is installed,
and everything except :func:`read_text` works without it.
"""

import importlib.util
import io
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MIN_CONF = 0.5          # prices below this OCR confidence are ignored
BADGE_MIN_CONF = 0.3    # a misread badge cannot pass the check against two prices, so it may be noisier
NAME_MIN_CONF = 0.4     # name lines are noisier; a bad word is less costly than a bad price
PCT_TOLERANCE = 1.0     # flyers round the badge inconsistently (13.9% printed as 13%)

# Layout, as fractions of image size, measured on Cometa's badge flyers:
# badge above the product photo, "de"/"por" bubble ~0.11 of the height below it,
# product name in the lines just left of the bubble.
CELL_LEFT = 0.02        # price may start this far left of the badge
CELL_WIDTH = 0.25       # ... and this far right of it
CELL_HEIGHT = 0.20      # ... and this far below it
NAME_WIDTH = 0.22       # name lines start at most this far left of the "de" price
NAME_MARGIN_X = 0.012
NAME_MARGIN_Y = 0.013

_PCT_RE = re.compile(r"^(\d{1,2})\s*%$")
_LABEL_RE = re.compile(r"^\W*\d?\W*(de|por|c[aeo]d[ae])\W*$", re.IGNORECASE)  # "De:", "Por:", "Cada"/"Cade"
_LETTER_RE = re.compile(r"[^\W\d_]")
_ZERO_AS_O_RE = re.compile(r"(?<=\d)O(?=\d|\s?(?:g|kg|ml|L)\b)")  # "20Og" -> "200g"
# The one-kilo size is often misread as a word: "Jko", "lkg", "1ko" (a 1 read as J/l/I, the g as o/q/0).
# Only a token that is nothing but that shape is changed, so real words are left alone.
_ONE_KILO_RE = re.compile(r"(?<![\w.,])[1IlJj|]\s?k[gqo0](?![\w])")


@dataclass(frozen=True)
class TextBox:
    """One piece of OCR'd text with its pixel bounding box."""
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class FlyerOffer:
    name: str
    price: float
    regular_price: float
    discount_pct: int


def ocr_available() -> bool:
    return importlib.util.find_spec("easyocr") is not None


_reader = None


def read_text(image_bytes: bytes) -> Tuple[List[TextBox], int, int]:
    """OCR an image; returns its text boxes and its (width, height).

    Needs ``easyocr`` (``pip install -r requirements-ocr.txt``). The first call
    loads the model, and downloads it if it is not cached yet.
    """
    global _reader
    import easyocr
    from PIL import Image

    if _reader is None:
        _reader = easyocr.Reader(["pt"], gpu=False, verbose=False)
    width, height = Image.open(io.BytesIO(image_bytes)).size
    boxes = []
    for corners, text, conf in _reader.readtext(image_bytes):
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        boxes.append(TextBox(text, float(conf), float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))))
    return boxes, width, height


def parse_price(text: str) -> Optional[float]:
    """'4,99' -> 4.99, and '499' -> 4.99 (OCR often drops the comma).

    Anything containing letters ("350g", "15g") is not a price.
    """
    if _LETTER_RE.search(text):
        return None
    digits = re.sub(r"[^\d,.]", "", text)
    match = re.fullmatch(r"(\d{1,3})[.,](\d{2})", digits) or re.fullmatch(r"(\d{1,3}?)(\d{2})", digits)
    if not match:
        return None
    return float(f"{int(match.group(1))}.{match.group(2)}")


def _consistent(regular: float, price: float, pct: int) -> bool:
    return regular > price and abs((1 - price / regular) * 100 - pct) < PCT_TOLERANCE


def _name_near(boxes: List[TextBox], de: TextBox, por: TextBox, width: int, height: int) -> str:
    """The text lines just left of a "de"/"por" bubble, top to bottom."""
    candidates = [
        b for b in boxes
        if b.conf >= NAME_MIN_CONF
        and b.x1 <= de.x0 + NAME_MARGIN_X * width
        and b.x0 >= de.x0 - NAME_WIDTH * width
        and b.y0 >= de.y0 - NAME_MARGIN_Y * height
        and b.y1 <= por.y1 + NAME_MARGIN_Y * height
        and _LETTER_RE.search(b.text)          # drops stray price fragments ("35", "99 09")
        and not _LABEL_RE.match(b.text)
    ]
    candidates.sort(key=lambda b: (b.y0 + b.y1) / 2)
    lines: List[List[TextBox]] = []
    for box in candidates:
        centre = (box.y0 + box.y1) / 2
        if lines and centre - _centre(lines[-1][0]) <= 0.6 * (box.y1 - box.y0):
            lines[-1].append(box)
        else:
            lines.append([box])
    words = [b.text.strip(" '\"`´“”") for line in lines for b in sorted(line, key=lambda b: b.x0)]
    return fix_units(" ".join(w for w in words if w))


def fix_units(name: str) -> str:
    """Repair sizes that OCR misreads: "20Og" -> "200g", "Jko" -> "1kg"."""
    return _ONE_KILO_RE.sub("1kg", _ZERO_AS_O_RE.sub("0", name))


def _centre(box: TextBox) -> float:
    return (box.y0 + box.y1) / 2


def extract_offers(boxes: List[TextBox], width: int, height: int) -> List[FlyerOffer]:
    """Turn OCR boxes into offers whose prices agree with their discount badge."""
    badges = [
        (b, int(m.group(1))) for b in boxes
        if b.conf >= BADGE_MIN_CONF and (m := _PCT_RE.match(b.text.strip()))
    ]
    priced = [(b, p) for b in boxes if b.conf >= MIN_CONF and (p := parse_price(b.text)) is not None]

    offers: List[FlyerOffer] = []
    used = set()
    for badge, pct in sorted(badges, key=lambda t: (t[0].y0, t[0].x0)):
        cell = [
            (b, p) for b, p in priced
            if b not in used
            and badge.x0 - CELL_LEFT * width <= b.x0 <= badge.x0 + CELL_WIDTH * width
            and badge.y1 <= b.y0 <= badge.y1 + CELL_HEIGHT * height
        ]
        pairs = [(de, por) for de in cell for por in cell if de[0] is not por[0] and _consistent(de[1], por[1], pct)]
        if len(pairs) != 1:
            logger.debug("Badge %d%% at (%d,%d): %d consistent price pairs, skipped",
                         pct, badge.x0, badge.y0, len(pairs))
            continue
        (de_box, de), (por_box, por) = pairs[0]
        name = _name_near(boxes, de_box, por_box, width, height)
        if len(_LETTER_RE.findall(name)) < 3:
            continue
        used.update((de_box, por_box))
        offers.append(FlyerOffer(name=name, price=por, regular_price=de, discount_pct=pct))

    logger.info("%d discount badges, %d offers verified against them", len(badges), len(offers))
    return offers


def read_offers(image_bytes: bytes) -> List[FlyerOffer]:
    """OCR a flyer image and return its verified offers."""
    boxes, width, height = read_text(image_bytes)
    return extract_offers(boxes, width, height)
