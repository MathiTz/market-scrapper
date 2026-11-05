"""A supermarket chain seen on the map in a region that we have no scraper for yet."""

from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint

from models.database import Base


class CandidateChain(Base):
    """Found by services/store_discovery.py. Never published: it only tells us which chains to build a scraper for.

    ``status`` is ``new`` until someone decides: ``planned`` (a scraper is wanted) or ``ignored`` (not worth it).
    A later discovery run updates the counts but leaves the status alone.
    """

    __tablename__ = "candidate_chains"
    __table_args__ = (UniqueConstraint("key", "state", name="uq_candidate_chain_key_state"),)

    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=False)  # the name with accents, noise words and branch suffixes removed
    state = Column(String, nullable=False)  # e.g. 'CE'
    name = Column(String, nullable=False)  # the spelling most places use
    branches = Column(Integer, nullable=False)
    cities = Column(String, nullable=True)
    example_address = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="new")
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
