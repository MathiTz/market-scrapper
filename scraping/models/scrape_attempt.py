"""Model for tracking scrape attempts (success/failure)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, Boolean

from models.database import Base


class ScrapeAttempt(Base):
    """Records a single scrape attempt for a site.

    Used for monitoring and health checks. Stores whether the scrape
    succeeded, how many items were found, and any error message.
    """

    __tablename__ = "scrape_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_key = Column(String(50), nullable=False, index=True)
    query = Column(String(200), nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error = Column(Text, nullable=True)
    items_found = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Float, nullable=True)
    run_id = Column(String(32), nullable=True)  # tags every price this run saved; None for older attempts
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ScrapeAttempt(site={self.site_key}, success={self.success}, "
            f"items={self.items_found}, error={self.error})>"
        )
