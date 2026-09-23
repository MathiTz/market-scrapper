"""Product model."""

from sqlalchemy import Column, Integer, String, Float, DateTime, func
from models.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    brand = Column(String, nullable=True)
    category = Column(String, nullable=True)
    unit = Column(String, nullable=True)  # e.g. 'kg', 'L', 'un'
    # The manufacturer's barcode and a photo, when a source actually gives them (VTEX stores' product
    # search API does, for free, in the same response already fetched for price - most scrapers still
    # don't and leave these null). Filled in once and kept: see _get_or_create_product's backfill-only
    # update, so a later scrape from a source with no evidence never erases a value an earlier one found.
    gtin = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name!r})>"
