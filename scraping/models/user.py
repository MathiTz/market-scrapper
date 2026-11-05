"""Shopper accounts: the local mirror of the production tables (scraping/db/schema.sql, api/src/accounts.ts).

Only the local Flask API writes these; the publisher never touches them. ``password_hash`` is
PBKDF2-SHA-256 and null for an account that only signed in with Google; ``google_sub`` is Google's
stable subject id.
"""

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, func

from models.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(254), nullable=False, unique=True, index=True)  # stored lower-cased
    password_hash = Column(String(255), nullable=True)
    name = Column(String(80), nullable=True)
    google_sub = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<User(id={self.id!r}, email={self.email!r})>"


class UserSession(Base):
    """An opaque session token: the row keeps only the SHA-256 of the cookie value."""

    __tablename__ = "sessions"

    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class UserPreference(Base):
    """One row per shopper: the place they compare prices from ("Perto de você") and the city they browse."""

    __tablename__ = "user_preferences"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    region = Column(String(80), nullable=False, default="Fortaleza")
    location_label = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    radius_km = Column(Integer, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class SavedList(Base):
    """A shopping list kept in the account; ``lines`` has the same shape as the browser's localStorage list."""

    __tablename__ = "saved_lists"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    lines = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
