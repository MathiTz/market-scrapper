"""Warehouse configuration, loaded from scraping/.env like the rest of the project."""

import os
from pathlib import Path

from dotenv import load_dotenv

from config import BASE_DIR

load_dotenv(BASE_DIR / ".env")


def _path(value: str, default: Path) -> Path:
    candidate = Path(value) if value else default
    return candidate if candidate.is_absolute() else BASE_DIR / candidate


WAREHOUSE_DB = _path(os.getenv("WAREHOUSE_DB", ""), BASE_DIR / "warehouse.db")
TAXONOMY_DIR = BASE_DIR / "data" / "cosmos-categorias"
TAXONOMY_CSV = TAXONOMY_DIR / "categorias.csv"

# NCM: the official table (vendored) and the curated category map. See warehouse/ncm.py.
NCM_DIR = _path(os.getenv("NCM_DIR", ""), BASE_DIR / "data" / "ncm")
NCM_TABLE_CSV = NCM_DIR / "ncm.csv"
NCM_CATEGORY_CSV = NCM_DIR / "category-ncm.csv"

# A barcode's own NCM can only come from a paid provider (a GTIN does not encode one). Kept here
# so enabling it is an .env change, not a code change.
COSMOS_API_TOKEN = os.getenv("COSMOS_API_TOKEN", "")
COSMOS_GTIN_URL = os.getenv("COSMOS_GTIN_URL", "https://api.cosmos.bluesoft.com.br/gtins").rstrip("/")


# Generative model for the free-form part (choosing a leaf from the whole tree).
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_CLOUD_BASE_URL = os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com").rstrip("/")
LLM_MODEL = os.getenv("WAREHOUSE_LLM_MODEL", "gemma4:31b")
LLM_BATCH_SIZE = int(os.getenv("WAREHOUSE_LLM_BATCH_SIZE", "10"))
PROMPT_VERSION = os.getenv("WAREHOUSE_PROMPT_VERSION", "v1")

# Products that are not food or drink have no Cosmos node: they get this synthetic leaf so the
# warehouse can still say "classified, and deliberately outside the grocery taxonomy".
OUTSIDE_SLUG = "fora-da-taxonomia"
OUTSIDE_NAME = "Fora da taxonomia (não alimentício)"
