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
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "10000"))
SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "12"))

# --- Publishing ---
# How many products of each chain the published snapshot carries (0 = all of them). The browser downloads the
# whole snapshot, so a chain with tens of thousands of products cannot all go in it; with a cap, the offers and
# the products several chains sell come first, and the rest is found through the full-catalogue search
# (GET /api/search, fed by services/listings.py). Turn it on only once the deployed web app has that search.
SNAPSHOT_OFFERS_PER_CHAIN = int(os.getenv("SNAPSHOT_OFFERS_PER_CHAIN", "0"))
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