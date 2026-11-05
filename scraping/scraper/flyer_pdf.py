"""Offers read from the text layer of a retail flyer PDF (Mix Mateus's, made by a flyer generator).

Unlike Cometa's flyers (flat images, read by OCR in :mod:`scraper.flyer_ocr`), these PDFs hold real text, so a
price is exact. What the file gives is words with a position and a size, not products, so a product is built
from the layout the generator uses. A price is the token ``R$``, then a much bigger integer, then the cents
in a smaller size, then a unit word ("cada", "quilo") below; its name is the block of small text just above
it (or, in a few layouts, beside it). Fonts differ from one flyer template to the next, so only sizes and
positions are used, relative to the page's width (a flyer is A4 or A3).

A reading is kept only when it is unambiguous: a price with no name block, a name block claimed by a nearer
price, or a price that applies only "com o CPF no caixa" (a member price) is left out rather than guessed.
"""

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

A4_WIDTH = 595.0  # sizes below are in points on an A4-wide page and scale with the page's width

_INTEGER = re.compile(r"\d{1,3}")
_CENTS = re.compile(r"\d{2}")
_WHOLE_PRICE = re.compile(r"(\d{1,3}),(\d{2})")  # a price the generator set in one run: "10,90"
_UNITS = {"cada": "", "un": "", "unid": "", "unidade": "", "quilo": " (kg)", "kg": " (kg)"}
# Words that make a block of small print something other than a product name
_NOT_A_NAME = re.compile(
    r"\b(cpf|limite|unid\w*|desconto|promo[cç][aã]o|caixa|nesta|oferta|ofertas|v[aá]lid[ao]s?|estoque|estoques|"
    r"economize|app|whatsapp|qr)\b", re.IGNORECASE,
)
# Section titles of a flyer ("Bazar", "Limpeza e Higiene"): small print too, but never a product
_HEADINGS = frozenset({
    "bazar", "mercearia", "padaria", "pet", "limpeza e higiene", "limpeza", "higiene", "hortifruti", "acougue", "peixaria",
    "bebidas", "frios", "laticinios", "congelados", "perfumaria", "utilidades", "carnes", "frios e laticinios", "mercearia doce",
})
_MIN_NAME_SIZE, _MAX_NAME_SIZE = 4.2, 10.8  # product-name print, in A4 points: headlines are bigger, legal text rarely fits
_MAX_PAIR_DISTANCE = 42.0  # in A4 points: further than this a block is not the name of that price


@dataclass(frozen=True)
class FlyerOffer:
    name: str
    price: float


@dataclass
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float

    @property
    def mid_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class _Price:
    value: float
    x0: float
    x1: float
    top: float
    bottom: float
    int_size: float
    suffix: str = ""  # " (kg)" for a price per kilo

    def contains_center(self, word: _Word) -> bool:
        """Whether the word's middle falls inside the price's box (a name may touch the box without being in it)."""
        return self.x0 <= word.mid_x <= self.x1 and self.top <= (word.top + word.bottom) / 2 <= self.bottom


@dataclass
class _Block:
    words: List[_Word]

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def size(self) -> float:
        return max(w.size for w in self.words)

    def text(self) -> str:
        lines: List[List[_Word]] = []
        for w in sorted(self.words, key=lambda w: (w.top, w.x0)):
            if lines and abs(lines[-1][0].top - w.top) < 0.5 * w.size:
                lines[-1].append(w)
            else:
                lines.append([w])
        return " ".join(" ".join(w.text for w in sorted(line, key=lambda w: w.x0)) for line in lines)


def read_offers(pdf: bytes) -> List[FlyerOffer]:
    """Every offer the flyer's text layer holds, across its pages; none if it is a flat image."""
    import pdfplumber  # imported here: only the chains that publish such flyers need it

    offers: List[FlyerOffer] = []
    with pdfplumber.open(io.BytesIO(pdf)) as document:
        for number, page in enumerate(document.pages, start=1):
            try:
                words = [
                    _Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"], w["size"])
                    for w in page.extract_words(extra_attrs=["size"])
                ]
                offers.extend(read_page(words, page.width / A4_WIDTH))
            except Exception as exc:  # one bad page must not lose the rest of the flyer
                logger.warning("Could not read flyer page %d: %s", number, exc)
    return offers


def read_page(words: List[_Word], scale: float) -> List[FlyerOffer]:
    prices = [p for p in _prices(words, scale) if not _for_cpf_holders(p, words, scale)]
    blocks = _name_blocks(words, prices, scale)
    pairs = _pair(prices, blocks, scale)
    offers = []
    for price, block in pairs:
        name = " ".join(block.text().split())
        if sum(c.isalpha() for c in name) >= 3:
            offers.append(FlyerOffer(name + price.suffix, price.value))
    return offers


def _prices(words: List[_Word], scale: float) -> List[_Price]:
    prices = []
    for sign in (w for w in words if w.text == "R$"):
        integer = _price_integer(sign, words, scale)
        if integer is None:
            continue
        whole = _WHOLE_PRICE.fullmatch(integer.text)
        cents = None if whole else _price_cents(integer, words, scale)
        if whole:
            value = int(whole.group(1)) + int(whole.group(2)) / 100
            parts = [sign, integer]
        elif cents is not None:
            value = int(integer.text) + int(cents.text) / 100
            parts = [sign, integer, cents]
        else:
            continue
        unit = _price_unit(parts, words, scale)
        if unit is not None:
            parts.append(unit)
        if value <= 0:
            continue
        suffix = _UNITS.get(unit.text.lower().strip(".,"), "") if unit is not None else ""
        prices.append(_Price(
            value=round(value, 2), x0=min(w.x0 for w in parts), x1=max(w.x1 for w in parts),
            top=min(w.top for w in parts), bottom=max(w.bottom for w in parts), int_size=integer.size, suffix=suffix,
        ))
    return prices


def _price_integer(sign: _Word, words: List[_Word], scale: float) -> Optional[_Word]:
    """The big number right after an ``R$``: much larger print, starting where the ``R$`` ends."""
    candidates = [
        w for w in words
        if (_INTEGER.fullmatch(w.text) or _WHOLE_PRICE.fullmatch(w.text)) and w.size >= 1.8 * sign.size
        and sign.x1 - 3 * scale <= w.x0 <= sign.x1 + 5 * scale
        and w.top - 2 * scale <= sign.top <= w.bottom
    ]
    return min(candidates, key=lambda w: w.x0, default=None)


def _price_cents(integer: _Word, words: List[_Word], scale: float) -> Optional[_Word]:
    """The cents: two digits in a smaller size, right after the integer and level with its top."""
    candidates = [
        w for w in words
        if _CENTS.fullmatch(w.text) and w.size < integer.size * 0.85
        and integer.x1 - 2 * scale <= w.x0 <= integer.x1 + 0.7 * integer.size
        and integer.top - 4 * scale <= w.top <= integer.top + 0.6 * integer.size
    ]
    return min(candidates, key=lambda w: w.x0, default=None)


def _price_unit(parts: List[_Word], words: List[_Word], scale: float) -> Optional[_Word]:
    """The small word under the price saying what it is for ("cada", "quilo")."""
    x0, x1 = min(w.x0 for w in parts), max(w.x1 for w in parts)
    bottom = max(w.bottom for w in parts)
    candidates = [
        w for w in words
        if w.text.lower().strip(".,") in _UNITS and w.x1 >= x0 - 2 * scale and w.x0 <= x1 + 2 * scale
        and bottom - 0.6 * max(p.size for p in parts) <= w.top <= bottom + 8 * scale
    ]
    return min(candidates, key=lambda w: abs(w.top - bottom), default=None)


def _for_cpf_holders(price: _Price, words: List[_Word], scale: float) -> bool:
    """A price printed under "COM O CPF NO CAIXA" is for members only: it is not the shelf price."""
    return any(
        w.text.upper() == "CPF" and price.x0 - 25 * scale <= w.mid_x <= price.x1 + 25 * scale
        and -2 * scale <= price.top - w.bottom <= 0.5 * price.int_size
        for w in words
    )


def _name_blocks(words: List[_Word], prices: List[_Price], scale: float) -> List[_Block]:
    """Runs of small print that could be a product name: neither part of a price nor a headline."""
    small = [
        w for w in words
        if _MIN_NAME_SIZE * scale <= w.size <= _MAX_NAME_SIZE * scale and not any(p.contains_center(w) for p in prices)
    ]
    small.sort(key=lambda w: (w.top, w.x0))
    parent = list(range(len(small)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(small):
        for j in range(i + 1, len(small)):
            b = small[j]
            if b.top - a.bottom > 1.6 * scale * 3:
                break  # sorted by top: nothing further down can touch a
            if _same_block(a, b, scale):
                parent[find(j)] = find(i)
    groups: Dict[int, List[_Word]] = {}
    for i, w in enumerate(small):
        groups.setdefault(find(i), []).append(w)
    blocks = [_Block(g) for g in groups.values()]
    return [b for b in blocks if not _NOT_A_NAME.search(b.text()) and _plain(b.text()) not in _HEADINGS]


def _plain(text: str) -> str:
    """Lower case without accents or punctuation, for comparing a printed word with a list."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", folded).split())


def _same_block(a: _Word, b: _Word, scale: float) -> bool:
    size = max(a.size, b.size)
    same_line = abs(a.top - b.top) < 0.45 * size
    if same_line:
        gap = max(b.x0 - a.x1, a.x0 - b.x1)
        return gap < 0.9 * size
    next_line = 0 < b.top - a.top < 2.2 * size and b.top - a.bottom < 0.95 * size
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    return next_line and overlap > -0.2 * size and abs(a.mid_x - b.mid_x) < 9 * size


def _pair(prices: List[_Price], blocks: List[_Block], scale: float) -> List[Tuple[_Price, _Block]]:
    """Each price with the block of text nearest above it (or beside it), one block per price."""
    options = []
    for p in prices:
        for b in blocks:
            cost = _distance(p, b, scale)
            if cost is not None and cost <= _MAX_PAIR_DISTANCE * scale:
                options.append((cost, id(p), id(b), p, b))
    options.sort(key=lambda o: o[:3])
    taken_prices, taken_blocks, pairs = set(), set(), []
    for _, _, _, p, b in options:
        if id(p) in taken_prices or id(b) in taken_blocks:
            continue
        taken_prices.add(id(p))
        taken_blocks.add(id(b))
        pairs.append((p, b))
    return pairs


def _distance(price: _Price, block: _Block, scale: float) -> Optional[float]:
    """How far the block is from being the price's name, or None when it cannot be."""
    horizontal = max(0.0, block.x0 - price.x1, price.x0 - block.x1)
    # Only the part of the block over the price's own columns says whether it sits above it: a size line
    # printed to the left of the "R$" ("21,5cm") is level with the price without the name being beside it.
    over = [w for w in block.words if w.x1 > price.x0 and w.x0 < price.x1]
    above = price.top - max(w.bottom for w in over) if over else price.top - block.bottom
    if above >= -6 * scale:  # a name sits over its price, touching it or overlapping its top edge a little
        if horizontal > 0.6 * (price.x1 - price.x0) + 8 * scale:
            return None
        return max(above, 0.0) + 1.5 * horizontal
    # beside: level with the price, to its left or right
    level = block.top < price.bottom and block.bottom > price.top
    if level and horizontal > 0:
        return 12 * scale + horizontal + 1.5 * abs(block.top - price.top) / 4
    return None
