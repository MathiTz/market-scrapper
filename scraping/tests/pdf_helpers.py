"""A tiny PDF builder for tests: text at given positions and sizes, no images, nothing to download."""

from typing import List, Tuple

# (x from the left, top from the page's top, font size, text)
Text = Tuple[float, float, float, str]


def make_pdf(texts: List[Text], width: float = 595.0, height: float = 842.0) -> bytes:
    """A one-page PDF with a real text layer, like the flyers whose prices ``scraper.flyer_pdf`` reads."""
    stream = "".join(
        f"BT /F1 {size} Tf {x} {height - top - size * 0.8:.2f} Td ({_escape(text)}) Tj ET\n"
        for x, top, size, text in texts
    ).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents 4 0 R "
        f"/Resources << /Font << /F1 5 0 R >> >> >>".encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def product(x: float, top: float, name_lines: List[str], integer: str, cents: str, unit: str = "cada") -> List[Text]:
    """One product cell as the flyers print it: the name above, then ``R$``, a big integer, small cents, the unit."""
    texts: List[Text] = []
    for i, line in enumerate(name_lines):
        texts.append((x, top + i * 8, 7 if i == 0 else 6, line))
    price_top = top + len(name_lines) * 8 + 10
    texts += [
        (x, price_top + 8, 7, "R$"),
        (x + 9, price_top, 33, integer),
        (x + 10 + 0.556 * 33 * len(integer), price_top + 2, 15, cents),  # Helvetica digits are 0.556 em wide
        (x + 12, price_top + 24, 5, unit),
    ]
    return texts


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
