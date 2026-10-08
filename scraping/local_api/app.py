"""Local Flask API: mirrors api/ (the production Hono app) for local development, plus scrape/health/
diagnose endpoints that have no production equivalent.

Everything this serves is JSON - there is no server-rendered page here. See web/AGENTS.md for the
frontend, and web/vite.config.ts's proxy for how the two are wired together in local development.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `config` can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hashlib
import json
import logging
import math
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

from flask import Flask, Response, jsonify, request
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import HOST, PORT, DEBUG, SECRET_KEY
from models.database import SessionLocal, init_db
from models.scrape_attempt import ScrapeAttempt
from services.address_search import (
    MAX_QUERY, MIN_QUERY, AddressSearchError, normalize, reverse_address, search_addresses,
)
from services.public_api import build_public
from services.scraper_service import run_and_store, run_all_products, run_all_offers
from diagnose_sites import run_diagnosis

# Receipt OCR (scraping/receiptocr/) is optional like Cometa's easyocr: without it the
# API still serves everything else, and /api/receipt/ocr explains itself with a 503.
_receipt_ocr_import_error = None
try:
    from receiptocr import ReceiptExtractor
except ImportError as _err:
    ReceiptExtractor = None
    _receipt_ocr_import_error = str(_err)

try:
    from receiptocr.schemas import (
        AuthenticationError, BadReplyError, BadRequestError, ModelNotFoundError,
        ProviderUnavailableError, QuotaError, RateLimitedError, ReceiptOcrError,
    )
except ImportError:
    # Stub the hierarchy so the route's except-clauses still name valid types when
    # the optional package (or cv2) is missing; the route returns 503 before using them.
    ReceiptOcrError = type("ReceiptOcrError", (Exception,), {})  # type: ignore[misc]
    AuthenticationError = type("AuthenticationError", (ReceiptOcrError,), {})  # type: ignore[misc]
    QuotaError = type("QuotaError", (ReceiptOcrError,), {})  # type: ignore[misc]
    RateLimitedError = type("RateLimitedError", (ReceiptOcrError,), {})  # type: ignore[misc]
    ProviderUnavailableError = type("ProviderUnavailableError", (ReceiptOcrError,), {})  # type: ignore[misc]
    BadReplyError = type("BadReplyError", (ReceiptOcrError,), {})  # type: ignore[misc]
    ModelNotFoundError = type("ModelNotFoundError", (ReceiptOcrError,), {})  # type: ignore[misc]
    BadRequestError = type("BadRequestError", (ReceiptOcrError,), {})  # type: ignore[misc]


# Configure logging to see what's happening during scraping
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY

init_db()


def get_db() -> Session:
    return SessionLocal()


@app.route("/diagnose")
def diagnose():
    """Run site diagnosis and return the saved JSON files."""
    try:
        files = run_diagnosis()
        data = {}
        for f in files:
            with open(f, "r", encoding="utf-8") as fh:
                data[Path(f).stem] = json.load(fh)
        return jsonify({"status": "ok", "files": files, "data": data})
    except Exception as exc:
        logger.exception("Diagnosis failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/scrape")
def scrape():
    """Scrape products or offers.

    Defaults to scraping all offers pages so we grab every available product,
    not a specific query. Pass ``query`` to search for one product, or
    ``mode=products`` to iterate over seeded products in the database.
    If ``debug`` param is true, return the raw scraped products without saving.
    """
    query = request.args.get("query", "").strip()
    site = request.args.get("site")
    mode = request.args.get("mode", "").lower()
    debug = request.args.get("debug", "false").lower() in ("true", "1", "yes")

    logger.info("Scrape request: query=%r site=%r mode=%r debug=%r", query, site, mode, debug)

    try:
        if debug:
            # Return raw products without saving
            from scraper.sites import ALL_SCRAPERS, SCRAPER_MAP

            if site:
                scraper_cls = SCRAPER_MAP.get(site)
                if not scraper_cls:
                    return jsonify({"status": "error", "message": f"Unknown site '{site}'"}), 400
                scrapers = [scraper_cls]
            else:
                scrapers = ALL_SCRAPERS

            all_products = {}
            for scraper_cls in scrapers:
                scraper = scraper_cls()
                logger.info("Debug scraping %s...", scraper.site_name)
                try:
                    results = scraper.scrape(query, limit=1000)
                    all_products[scraper.site_key] = [
                        {
                            "store_name": p.store_name,
                            "product_name": p.product_name,
                            "price": p.price,
                            "url": p.url,
                        }
                        for p in results
                    ]
                    logger.info("%s returned %d products", scraper.site_name, len(results))
                except Exception as exc:
                    logger.exception("Debug scrape failed for %s", scraper.site_name)
                    all_products[scraper.site_key] = {"error": str(exc)}
            return jsonify({"status": "ok", "products": all_products})

        if query:
            count = run_and_store(query, site=site)
            return jsonify({"status": "ok", "saved": count})
        elif mode == "products":
            # Explicitly iterate seeded products; default is offers so we don't
            # accidentally restrict scraping to a hardcoded product list.
            count = run_all_products(site=site)
            return jsonify({"status": "ok", "saved": count})
        else:
            # Default: scrape all offers pages from every configured site.
            results = run_all_offers(site=site)
            return jsonify({"status": "ok", "saved_by_site": results, "total": sum(results.values())})
    except Exception as exc:
        logger.exception("Scrape failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/health")
def health():
    """Return health status: DB connectivity and last scrape attempts."""
    db = get_db()
    try:
        # Simple DB check
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    try:
        # Get latest attempt per site
        attempts = (
            db.query(ScrapeAttempt)
            .order_by(ScrapeAttempt.created_at.desc())
            .limit(100)
            .all()
        )
        latest_by_site = {}
        for attempt in attempts:
            if attempt.site_key not in latest_by_site:
                latest_by_site[attempt.site_key] = {
                    "success": attempt.success,
                    "error": attempt.error,
                    "created_at": attempt.created_at.isoformat(),
                    "items_found": attempt.items_found,
                    "duration_ms": attempt.duration_ms,
                }
    except Exception:
        latest_by_site = {}
    finally:
        db.close()

    return jsonify({
        "status": "ok" if db_status == "ok" else "error",
        "database": db_status,
        "latest_scrapes": latest_by_site,
    })


@app.route("/scrape/status")
def scrape_status():
    """The last 100 scrape attempts, newest first (site, success, error, items found, duration)."""
    db = get_db()
    try:
        attempts = (
            db.query(ScrapeAttempt)
            .order_by(ScrapeAttempt.created_at.desc())
            .limit(100)
            .all()
        )
        return jsonify([
            {
                "site_key": a.site_key, "success": a.success, "error": a.error,
                "items_found": a.items_found, "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat(),
            }
            for a in attempts
        ])
    finally:
        db.close()


# /api/public scans every price and matches products, and the data only changes when a scrape
# finishes, so each filter combination is built once a minute; browsers may reuse it as well.
PUBLIC_CACHE_SECONDS = 60
PUBLIC_CACHE_MAX_ENTRIES = 32  # a typed search is a key, and each payload can be several MB
_public_cache: "OrderedDict[tuple, tuple[float, bytes, str]]" = OrderedDict()
_public_cache_lock = threading.Lock()


def _public_body(key: tuple, build) -> tuple:
    """(JSON body, ETag) for a filter combination, rebuilt at most once per PUBLIC_CACHE_SECONDS."""
    with _public_cache_lock:
        hit = _public_cache.get(key)
        if hit and time.monotonic() - hit[0] < PUBLIC_CACHE_SECONDS:
            return hit[1], hit[2]
        body = app.json.dumps(build()).encode("utf-8")
        etag = hashlib.md5(body).hexdigest()
        _public_cache[key] = (time.monotonic(), body, etag)
        _public_cache.move_to_end(key)
        while len(_public_cache) > PUBLIC_CACHE_MAX_ENTRIES:
            _public_cache.popitem(last=False)
        return body, etag


@app.route("/api/public")
def api_public():
    """Products, offers and flyers for the Mercado em Dia UI (see services/public_api.py)."""
    args = request.args
    filters = {name: args.get(name, "") for name in ("q", "network", "channel", "category", "product")}

    def build():
        db = get_db()
        try:
            return build_public(db, **filters)
        finally:
            db.close()

    try:
        body, etag = _public_body(tuple(filters.values()), build)
    except Exception:
        logger.exception("GET /api/public failed")
        return jsonify({"error": "Não foi possível carregar as ofertas agora."}), 500
    response = Response(body, mimetype="application/json")
    response.set_etag(etag)
    response.headers["Cache-Control"] = f"public, max-age={PUBLIC_CACHE_SECONDS}, stale-while-revalidate=300"
    return response.make_conditional(request)


@app.route("/api/location", methods=["POST"])
def api_location():
    """Address search for the UI's "Perto de você" filter: ``{"query": "..."}`` -> ``{"places": [...]}``."""
    query = normalize((request.get_json(silent=True) or {}).get("query") or "")
    if not MIN_QUERY <= len(query) <= MAX_QUERY:
        return jsonify({"error": f"Digite entre {MIN_QUERY} e {MAX_QUERY} caracteres do endereço ou bairro."}), 400
    try:
        return jsonify({"places": search_addresses(query)})
    except AddressSearchError:
        logger.warning("Address search is unavailable")  # the query is not logged: it is what the person typed
        return jsonify({"error": "A busca de endereço está indisponível agora. Tente de novo ou use sua localização."}), 502


@app.route("/api/location/reverse")
def api_location_reverse():
    """The street address for a GPS position: ``?lat=..&lon=..`` -> ``{"place": {...} | null}``."""
    try:
        latitude, longitude = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Coordenadas inválidas."}), 400
    if not (math.isfinite(latitude) and math.isfinite(longitude) and abs(latitude) <= 90 and abs(longitude) <= 180):
        return jsonify({"error": "Coordenadas inválidas."}), 400
    try:
        return jsonify({"place": reverse_address(latitude, longitude)})
    except AddressSearchError:
        logger.warning("Reverse address lookup is unavailable")  # the coordinates are not logged
        return jsonify({"error": "Não foi possível descobrir o endereço agora."}), 502


@app.route("/api/session", methods=["GET", "POST", "DELETE"])
def api_session():
    """Placeholder for the admin login (the UI expects these answers until real accounts exist)."""
    if request.method == "GET":
        return jsonify({"actor": None})
    if request.method == "DELETE":
        return jsonify({"ok": True})
    return jsonify({"error": "Login depende da integração com o backend."}), 501


# A receipt photo is a phone camera shot; 10 MB is generous for a JPEG that only
# needs to stay legible after the OCR tiles are cut from it.
RECEIPT_MAX_BYTES = 10 * 1024 * 1024


def _is_valid_image(blob: bytes) -> bool:
    """Check if the provided bytes represent a decodable image.

    cv2 is guaranteed importable here: the route already returned 503 when the
    optional OCR dependencies are missing, and importing receiptocr imports cv2.
    """
    import cv2
    import numpy as np
    return cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR) is not None


@app.route("/api/receipt/ocr", methods=["POST"])
def api_receipt_ocr():
    """Read a Brazilian NFC-e receipt photo (scraping/receiptocr/) and return its items.

    ``multipart/form-data`` with the file in the ``image`` field. The
    extractor calls the ollama.com cloud vision API, so this needs
    ``OLLAMA_API_KEY`` in the environment (or scraping/.env) and the optional
    OCR dependencies from requirements-ocr.txt.
    """
    if ReceiptExtractor is None:
        logger.warning("Receipt OCR unavailable (missing optional dependency): %s", _receipt_ocr_import_error)
        return jsonify({"error": "O OCR de cupons não está instalado. Instale requirements-ocr.txt."}), 503

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "Envie uma imagem do cupom no campo 'image'."}), 400
    blob = file.read()
    if not blob:
        return jsonify({"error": "Envie uma imagem do cupom no campo 'image'."}), 400
    if len(blob) > RECEIPT_MAX_BYTES:
        return jsonify({"error": "A imagem do cupom é grande demais (máximo 10 MB)."}), 413
    if not _is_valid_image(blob):
        return jsonify({"error": "Envie uma imagem válida do cupom (PNG ou JPEG)."}), 400

    path = ""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        suffix = ".jpg"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(blob)
            path = tmp.name
        receipt = ReceiptExtractor().extract(path)
    except ReceiptOcrError as exc:
        logger.warning("Receipt OCR failed: %s", exc)
        if isinstance(exc, RateLimitedError):
            headers = {}
            if getattr(exc, "retry_after", None) is not None:
                headers["Retry-After"] = str(int(exc.retry_after))
            return jsonify({"error": "Muitas leituras de cupom agora. Tente de novo em instantes."}), 429, headers
        if isinstance(exc, BadRequestError):
            return jsonify({"error": "A leitura do cupom falhou. Verifique a imagem e tente de novo."}), 400
        # Two plain ReceiptOcrError messages are the caller's fault, not the provider's;
        # they are raised verbatim by receiptocr/__init__.py (extract()) - keep in sync.
        # The API key is never echoed: the message stays generic on purpose.
        if isinstance(exc, ReceiptOcrError) and exc.__class__ is ReceiptOcrError:
            message = str(exc)
            if message.startswith("Missing Ollama API key") or message.startswith("Unreadable image"):
                return jsonify({"error": "A leitura do cupom falhou. Verifique a imagem e tente de novo."}), 400
        if isinstance(exc, (AuthenticationError, QuotaError, BadReplyError, ProviderUnavailableError, ModelNotFoundError)):
            return jsonify({"error": "O serviço de leitura de cupons está indisponível agora."}), 502
        return jsonify({"error": "Não foi possível ler o cupom agora."}), 502
    except Exception:
        logger.exception("Receipt OCR failed unexpectedly")
        return jsonify({"error": "Não foi possível ler o cupom agora."}), 502
    finally:
        if path:
            Path(path).unlink(missing_ok=True)

    data = asdict(receipt)
    data["degraded"] = receipt.degraded
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=DEBUG, host=HOST, port=PORT)