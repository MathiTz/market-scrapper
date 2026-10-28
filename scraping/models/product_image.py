"""Locally mirrored product images.

One row per product, pointing at a 400 px WebP file under ``scraping/images``. Kept in a separate
table (not on ``products``) so the mirror can be recomputed and audited independently of the scrape
data, and so a rejected candidate leaves a trace instead of silently overwriting a good image.

See ``services/image_mirror.py`` for the flow that fills this in.
"""

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from models.database import Base


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, nullable=False, unique=True, index=True)

    sha256 = Column(String(64), nullable=False, index=True)  # content address: dedupes the same photo
    path = Column(String, nullable=False)                    # relative to scraping/
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    bytes = Column(Integer, nullable=False)

    # chain        - taken from the product's own page (trusted, not model-checked)
    # openfoodfacts- barcode (or name) lookup in Open Food Facts
    # chain_search - found by searching another chain's catalogue for the same name
    # web_search   - first usable result from an image search engine
    source_kind = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=True)

    status = Column(String, nullable=False, index=True)  # ok | flagged
    decision = Column(Text, nullable=True)               # JSON: per-criterion model probabilities
    model = Column(String, nullable=True)                # which decision model judged it, if any
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ProductImage(product_id={self.product_id}, {self.source_kind}, {self.status})>"
