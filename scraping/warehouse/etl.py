"""Warehouse ETL: ingest market.db products and classify them into the Cosmos taxonomy.

Read-only on the source, idempotent on the target, and every label keeps its provenance:

    python -m warehouse_etl --status
    python -m warehouse_etl --limit 50
    python -m warehouse_etl --rebuild-taxonomy
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from services.public_api import clean, display_name, match_tokens, parse_size
from warehouse import config, db
from warehouse.classifier import CloudClassifier, Result, path_of, signature
from warehouse.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

NOT_FOOD = config.OUTSIDE_SLUG


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- source


def load_products(connection, limit: Optional[int] = None,
                  product_id: Optional[int] = None) -> List[dict]:
    query = "select id, name, brand, gtin, image_url from products"
    params: tuple = ()
    if product_id is not None:
        query += " where id = ?"
        params = (product_id,)
    query += " order by id"
    if limit:
        query = f"{query} limit {int(limit)}"
    return [dict(row) for row in connection.execute(query, params)]


def normalize_gtin(gtin: Optional[str]) -> Optional[str]:
    """14-digit EAN, or None when the value is missing, malformed or an internal PLU."""
    digits = re.sub(r"\D", "", gtin or "")
    if len(digits) not in (8, 12, 13, 14):
        return None
    if len(digits) == 13 and digits.startswith("2"):  # GS1 variable-measure prefix
        return None
    return digits.zfill(14)


def canonical_key(product: dict) -> str:
    gtin = normalize_gtin(product.get("gtin"))
    if gtin:
        return f"gtin:{gtin}"
    tokens = sorted(match_tokens(product["name"]))
    amount, unit, pack = parse_size(product["name"])
    material = "|".join(tokens) + f"|{amount}{unit}x{pack}"
    return "tok:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- dimensions


def seed_taxonomy(connection, taxonomy: Taxonomy) -> int:
    """Mirror the CSV into dim_category (upsert). Returns the number of rows written."""
    version = f"cosmos-{len(taxonomy.nodes)}"
    rows = [(n.slug, n.name, n.path, n.parent_slug, n.depth, 1 if n.is_leaf else 0, "cosmos", version)
            for n in taxonomy.nodes.values()]
    rows.append((NOT_FOOD, config.OUTSIDE_NAME, config.OUTSIDE_NAME, None, 1, 1, "synthetic", version))
    connection.executemany(
        """insert into dim_category (slug, name, path, parent_slug, level, is_leaf, source, taxonomy_version)
           values (?, ?, ?, ?, ?, ?, ?, ?)
           on conflict(slug) do update set
             name=excluded.name, path=excluded.path, parent_slug=excluded.parent_slug,
             level=excluded.level, is_leaf=excluded.is_leaf, source=excluded.source,
             taxonomy_version=excluded.taxonomy_version""",
        rows,
    )
    return len(rows)


def seed_brands(connection, products: Sequence[dict]) -> None:
    brands = {(clean(p["brand"]), p["brand"].strip()) for p in products if (p.get("brand") or "").strip()}
    connection.executemany(
        """insert into dim_brand (brand_slug, brand_name) values (?, ?)
           on conflict(brand_slug) do nothing""",
        [(slug, name) for slug, name in brands if slug],
    )


# --------------------------------------------------------------------------- cache


def cached(connection, sig: str) -> Optional[dict]:
    row = connection.execute(
        "select answer_json from silver_llm_cache where input_signature_hash=? and prompt_version=? and method='cloud_leaf'",
        (sig, config.PROMPT_VERSION)).fetchone()
    return json.loads(row["answer_json"]) if row else None


def cache(connection, sig: str, model: str, answer: dict, confidence: float) -> None:
    connection.execute(
        """insert into silver_llm_cache
             (input_signature_hash, prompt_version, method, model, answer_json, confidence)
           values (?, ?, 'cloud_leaf', ?, ?, ?)
           on conflict(input_signature_hash, prompt_version, method) do update set
             answer_json=excluded.answer_json, confidence=excluded.confidence, model=excluded.model""",
        (sig, config.PROMPT_VERSION, model, json.dumps(answer, ensure_ascii=False), confidence),
    )


# --------------------------------------------------------------------------- classification


def classify(products: Sequence[dict], taxonomy: Taxonomy,
             workers: int = 4) -> Dict[int, Result]:
    """Classify the products in concurrent batches."""
    cloud = CloudClassifier(taxonomy)
    if not cloud.ready:
        raise SystemExit("OLLAMA_API_KEY is empty in scraping/.env; set it to classify.")
    batches = [list(products[i:i + cloud.batch_size])
               for i in range(0, len(products), cloud.batch_size)]
    results: Dict[int, Result] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(cloud.classify_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                answers = future.result() or {}
            except Exception as exc:  # noqa: BLE001 - one bad batch must not stop the run
                logger.warning("batch failed: %s", exc)
                answers = {}
            for product in batch:
                answer = answers.get(product["id"])
                if not answer:
                    continue
                results[product["id"]] = Result(
                    product["id"], answer["slug"], path_of(taxonomy, answer["slug"]),
                    "cloud", answer["confidence"], answer.get("reason", ""))
            done += len(batch)
            if done % (cloud.batch_size * 4) == 0 or done >= len(products):
                print(f"  classified {min(done, len(products))}/{len(products)}", flush=True)
    return results


def run(limit: Optional[int] = None, product_id: Optional[int] = None, force: bool = False,
        rebuild_taxonomy: bool = False, workers: int = 4) -> int:
    db.init()
    taxonomy = Taxonomy.load()
    connection = db.connect()
    try:
        if rebuild_taxonomy or connection.execute("select count(*) from dim_category").fetchone()[0] == 0:
            written = seed_taxonomy(connection, taxonomy)
            print(f"taxonomy: {written} categories ({taxonomy.leaf_count()} leaves) seeded")
            connection.commit()

        source = db.source_market()
        try:
            products = load_products(source, limit=limit, product_id=product_id)
        finally:
            source.close()
        if not products:
            print("no products selected")
            return 0

        seed_brands(connection, products)
        connection.commit()

        pending: List[dict] = []
        for product in products:
            sig = signature(product["name"], product.get("brand"))
            if not force and connection.execute(
                    "select 1 from silver_products where canonical_product_key=?",
                    (canonical_key(product),)).fetchone():
                continue
            answer = None if force else cached(connection, sig)
            pending.append({**product, "_cached": answer} if answer else product)
        print(f"{len(products)} product(s) selected, {len(pending)} to classify")

        fresh = [p for p in pending if "_cached" not in p]
        results: Dict[int, Result] = {}
        if fresh:
            results = classify(fresh, taxonomy, workers=workers)
            for product in fresh:
                result = results.get(product["id"])
                if result is None:
                    continue
                sig = signature(product["name"], product.get("brand"))
                cache(connection, sig, config.LLM_MODEL,
                      {"slug": result.slug, "confidence": result.confidence, "reason": result.reason},
                      result.confidence)

        written = 0
        for product in pending:
            if "_cached" in product:
                answer = product["_cached"]
                result = Result(product["id"], answer.get("slug"),
                                path_of(taxonomy, answer.get("slug") or ""),
                                "cache", float(answer.get("confidence") or 0.0),
                                answer.get("reason", ""))
            else:
                result = results.get(product["id"])
                if result is None:
                    connection.execute(
                        """insert into silver_category_review (source_product_id, raw_name, reason)
                           values (?, ?, 'no_answer')""",
                        (product["id"], product["name"]))
                    continue
            amount, unit, pack = parse_size(product["name"])
            review = "pending" if result.confidence < 0.7 else "none"
            if review == "pending":
                connection.execute(
                    """insert into silver_category_review
                         (source_product_id, raw_name, candidate_slug, candidate_path, confidence, reason)
                       values (?, ?, ?, ?, ?, 'low_confidence')""",
                    (product["id"], product["name"], result.slug, result.path, result.confidence))
            connection.execute(
                """insert into silver_products
                     (source_product_id, raw_name, display_name, raw_brand, gtin, identity_tokens_json,
                      amount, unit, pack_count, total_base_amount, is_variable_weight,
                      canonical_product_key, category_slug, category_path, category_source,
                      category_confidence, review_status, updated_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   on conflict(canonical_product_key) do update set
                     source_product_id=excluded.source_product_id,
                     raw_name=excluded.raw_name, display_name=excluded.display_name,
                     raw_brand=excluded.raw_brand, gtin=excluded.gtin,
                     identity_tokens_json=excluded.identity_tokens_json,
                     amount=excluded.amount, unit=excluded.unit, pack_count=excluded.pack_count,
                     total_base_amount=excluded.total_base_amount,
                     is_variable_weight=excluded.is_variable_weight,
                     canonical_product_key=excluded.canonical_product_key,
                     category_slug=excluded.category_slug, category_path=excluded.category_path,
                     category_source=excluded.category_source,
                     category_confidence=excluded.category_confidence,
                     review_status=excluded.review_status,
                     updated_at=excluded.updated_at""",
                (product["id"], product["name"], display_name(product["name"]),
                 (product.get("brand") or None), normalize_gtin(product.get("gtin")),
                 json.dumps(sorted(match_tokens(product["name"]))),
                 amount, unit, pack, amount * pack,
                 1 if unit == "g" and amount == 1000 and " kg" in f" {clean(product['name'])}" else 0,
                 canonical_key(product), result.slug, result.path, result.source,
                 result.confidence, review, now()))
            written += 1

        connection.execute(
            """insert into etl_watermarks
                 (pipeline_name, last_run_started_at, last_run_completed_at, last_status, rows_processed)
               values ('categorize', ?, ?, 'ok', ?)
               on conflict(pipeline_name) do update set
                 last_run_started_at=excluded.last_run_started_at,
                 last_run_completed_at=excluded.last_run_completed_at,
                 last_status='ok', rows_processed=excluded.rows_processed""",
            (now(), now(), written))
        connection.commit()
        print(f"wrote {written} product(s) into the warehouse")
        return 0
    finally:
        connection.close()


# --------------------------------------------------------------------------- status


def status() -> int:
    db.init()
    connection = db.connect()
    try:
        total = connection.execute("select count(*) from silver_products").fetchone()[0]
        review = connection.execute(
            "select count(*) from silver_category_review where status='pending'").fetchone()[0]
        outside = connection.execute(
            "select count(*) from silver_products where category_slug=?", (NOT_FOOD,)).fetchone()[0]
        source = db.source_market()
        try:
            products = source.execute("select count(*) from products").fetchone()[0]
        finally:
            source.close()
        print(f"source products: {products}")
        print(f"classified:      {total}  (outside taxonomy: {outside})")
        print(f"pending review:  {review}")
        print("\nby category:")
        for row in connection.execute(
                """select category_slug, count(*) n from silver_products
                   group by category_slug order by n desc limit 15"""):
            print(f"  {row['category_slug']:<40} {row['n']:>5}")
    finally:
        connection.close()
    return 0
