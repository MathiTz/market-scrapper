"""A real, physical branch of a chain (see :mod:`services.store_locations`)."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from models.database import Base


class StoreLocation(Base):
    """One real branch address, geocoded, used for actual "near you" distance.

    ``Store`` (see models/store.py) is one row per *chain*, not per branch, and its own ``address``/``lat``/
    ``lon`` are a single placeholder from the initial seed - never a real address. A chain with several
    physical branches (most of them) has several rows here, all sharing ``store_id``; a chain we have not
    found real branch data for yet has none, and the public API omits its location rather than guessing.
    """

    __tablename__ = "store_locations"
    __table_args__ = (UniqueConstraint("store_id", "external_id", name="uq_store_location_branch"),)

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    external_id = Column(String, nullable=False)  # the chain's own id for this branch, so a refresh updates it
    name = Column(String, nullable=False)  # branch name, e.g. "Porto das Dunas"
    address = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<StoreLocation(id={self.id}, store_id={self.store_id}, name={self.name!r})>"
