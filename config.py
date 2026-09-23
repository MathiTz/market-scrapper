"""Central configuration for the market scraper application."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'market.db'}")

# --- Scraping ---
DEFAULT_QUERY = os.getenv("DEFAULT_QUERY", "")
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "1000"))
SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "12"))
SCRAPE_MAX_RETRIES = int(os.getenv("SCRAPE_MAX_RETRIES", "3"))
SCRAPE_RETRY_BACKOFF = float(os.getenv("SCRAPE_RETRY_BACKOFF", "2.0"))
SCRAPE_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", "15"))

# --- Publishing ---
# Postgres connection string of the cloud database the Hono API reads (empty = do not publish).
# Use the owner/write role here; the API gets a separate read-only one.
PUBLISH_DATABASE_URL = os.getenv("PUBLISH_DATABASE_URL", "")

# --- Web ---
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5050"))
DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")