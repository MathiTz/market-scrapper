"""Price model - represents a price observation for a product at a store."""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from models.database import Base


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    price = Column(Float, nullable=False)
    unit = Column(String, nullable=True)  # e.g. 'kg', 'un', 'L'
    url = Column(String, nullable=True)
    regular_price = Column(Float, nullable=True)  # undiscounted price, when the site shows a deal
    offer = Column(String, nullable=True)  # the site's deal label, e.g. "25% OFF", "Leve 3 e pague 2"
    scraped_at = Column(DateTime, server_default=func.now())
    stock = Column(Integer, nullable=True)  # units the store said it had, when it said
    run_id = Column(String(32), nullable=True)  # the scrape run that saw this price (see ScrapeAttempt.run_id)

    product = relationship("Product", backref="prices")
    store = relationship("Store", backref="prices")

    def __repr__(self):
        return f"<Price(id={self.id}, price={self.price}, product_id={self.product_id}, store_id={self.store_id})>"
