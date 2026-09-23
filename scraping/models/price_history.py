"""Compact price history - superseded prices for a product at a store, packed instead of one row each.

See services/scraper_service.py's pack_entry/unpack_history for the binary format.
"""

from sqlalchemy import Column, ForeignKey, Integer, LargeBinary, DateTime, func
from models.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), primary_key=True)
    # A fixed-width packed binary series of past (price, observed-at) pairs, oldest first, capped at
    # HISTORY_CAP entries - see services/scraper_service.py. Not JSON: at thousands of products times
    # several observations a day, one text field name and punctuation repeated per entry adds up for
    # something nobody currently reads back except in bulk (a possible future price-trend view).
    blob = Column(LargeBinary, nullable=False, default=b"")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<PriceHistory(product_id={self.product_id}, store_id={self.store_id}, {len(self.blob)} bytes)>"
