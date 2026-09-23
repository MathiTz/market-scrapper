"""Store model."""

from sqlalchemy import Column, Integer, String, Float, DateTime, func
from models.database import Base


class Store(Base):
    """A chain (one row per chain name, not per physical branch - see StoreLocation for that).

    ``address``/``lat``/``lon``/``city``/``state``/``cep`` are not read by the public API: a chain usually
    has several real branches, not one, so its real, physical locations live in ``store_locations`` instead
    (see models/store_location.py and services/store_locations.py). These fields predate that and are kept
    only so a row written by an older seed is not an error; a new row does not need them filled in.
    """

    __tablename__ = "stores"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    chain = Column(String, nullable=True)  # e.g. 'Pão de Açúcar'
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    cep = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    website = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Store(id={self.id}, name={self.name!r})>"
