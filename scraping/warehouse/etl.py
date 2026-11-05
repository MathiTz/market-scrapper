"""Warehouse ETL: ingest market.db products and classify them into the Cosmos taxonomy.

Read-only on the source, idempotent on the target, and every label keeps its provenance:

    python -m warehouse_etl --status
    python -m warehouse_etl --limit 50
    python -m warehouse_etl --rebuild-taxonomy
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from services.identity import canonical_key, normalize_gtin
from services.public_api import clean, display_name, match_tokens, parse_size
from warehouse import config, db, ncm
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
        rebuild_taxonomy: bool = False, workers: int = 4, force_outside: bool = False) -> int:
    db.init()
    taxonomy = Taxonomy.load()
    connection = db.connect()
    try:
        if rebuild_taxonomy or connection.execute("select count(*) from dim_category").fetchone()[0] == 0:
            written = seed_taxonomy(connection, taxonomy)
            print(f"taxonomy: {written} categories ({taxonomy.leaf_count()} leaves) seeded")
            connection.commit()

        ncm_table = ncm.Table.load()
        category_codes = ncm.read_category_map(table=ncm_table)
        ncm.seed(connection, ncm_table, category_codes)
        connection.commit()
        gtin_codes = ncm.answers(connection)
        print(f"ncm: {len(ncm_table)} codes, {len(category_codes)} category code(s), "
              f"{len(gtin_codes)} barcode answer(s)")

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
            done = connection.execute(
                "select category_slug from silver_products where canonical_product_key=?",
                (canonical_key(product),)).fetchone()
            if done is not None and not force and not (force_outside and done["category_slug"] == NOT_FOOD):
                continue
            answer = None if (force or force_outside) else cached(connection, sig)
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
            ncm_answer = ncm.resolve(result.slug, normalize_gtin(product.get("gtin")),
                                     category_codes, gtin_codes)
            connection.execute(
                """insert into silver_products
                     (source_product_id, raw_name, display_name, raw_brand, gtin, identity_tokens_json,
                      amount, unit, pack_count, total_base_amount, is_variable_weight,
                      canonical_product_key, category_slug, category_path, category_source,
                      category_confidence, review_status, updated_at,
                      ncm_code, ncm_source, ncm_confidence, ncm_updated_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                     updated_at=excluded.updated_at,
                     ncm_code=excluded.ncm_code, ncm_source=excluded.ncm_source,
                     ncm_confidence=excluded.ncm_confidence, ncm_updated_at=excluded.ncm_updated_at""",
                (product["id"], product["name"], display_name(product["name"]),
                 (product.get("brand") or None), normalize_gtin(product.get("gtin")),
                 json.dumps(sorted(match_tokens(product["name"]))),
                 amount, unit, pack, amount * pack,
                 1 if unit == "g" and amount == 1000 and " kg" in f" {clean(product['name'])}" else 0,
                 canonical_key(product), result.slug, result.path, result.source,
                 result.confidence, review, now(),
                 ncm_answer.code if ncm_answer else None,
                 ncm_answer.source if ncm_answer else None,
                 ncm_answer.confidence if ncm_answer else None,
                 now() if ncm_answer else None))
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


# --------------------------------------------------------------------------- NCM only


def import_gtin_csv(path) -> int:
    """Store barcode -> NCM answers exported from a paid provider (Cosmos, GS1) or a manual sheet.

    Columns: ``gtin`` (or ``code``) and ``ncm`` (or ``ncm_code``). Rows with a code that is not in the
    official table are skipped, never stored. One GTIN answer is reused by every product that carries
    that barcode, so this is the only place a paid lookup has to be paid for.
    """
    import csv

    db.init()
    table = ncm.Table.load()
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = ncm.normalize_code(row.get("ncm") or row.get("ncm_code"))
            if code is None or not table.is_valid(code):
                continue
            rows.append((row.get("gtin") or row.get("code") or "", code))
    connection = db.connect()
    try:
        written = ncm.import_answers(connection, rows, source="csv")
        connection.commit()
    finally:
        connection.close()
    print(f"imported {written} barcode answer(s) from {path}")
    return 0


def apply_ncm() -> int:
    """Fill ``silver_products.ncm_*`` for everything already classified.

    Separate from :func:`run` on purpose: re-resolving a code is a local lookup, while re-running the
    run() would re-ask the model about products that are already classified. This is the pass to use
    after the category map or an imported barcode CSV changes.
    """
    db.init()
    table = ncm.Table.load()
    category_codes = ncm.read_category_map(table=table)
    connection = db.connect()
    try:
        ncm.seed(connection, table, category_codes)
        connection.commit()
        gtin_codes = ncm.answers(connection)
        rows = connection.execute(
            "select canonical_product_key, category_slug, gtin from silver_products").fetchall()
        updates = []
        for row in rows:
            answer = ncm.resolve(row["category_slug"], row["gtin"], category_codes, gtin_codes)
            if answer is None:
                continue  # nothing to say: keep whatever the product-level pass already wrote
            updates.append((answer.code, answer.source, answer.confidence, now(),
                            row["canonical_product_key"]))
        connection.executemany(
            """update silver_products
                  set ncm_code=?, ncm_source=?, ncm_confidence=?, ncm_updated_at=?
                where canonical_product_key=?""", updates)
        corrected = ncm.apply_product_overrides(connection, table=table)
        if corrected:
            print(f"ncm: {corrected} product(s) corrected from product-overrides.csv")
        connection.execute(
            """insert into etl_watermarks (pipeline_name, last_run_started_at, last_run_completed_at, last_status, rows_processed)
               values ('ncm', ?, ?, 'ok', ?)
               on conflict(pipeline_name) do update set
                 last_run_started_at=excluded.last_run_started_at,
                 last_run_completed_at=excluded.last_run_completed_at,
                 last_status='ok', rows_processed=excluded.rows_processed""",
            (now(), now(), len(updates)))
        connection.commit()
        covered = sum(1 for u in updates if u[0])
        print(f"ncm: {covered}/{len(updates)} product(s) have a code "
              f"({len(updates) - covered} still unmapped)")
        report_ncm(connection)
        return 0
    finally:
        connection.close()


def report_ncm(connection) -> None:
    total, covered = connection.execute(
        "select count(*), count(ncm_code) from silver_products").fetchone()
    if not total:
        return
    print(f"ncm coverage: {covered}/{total} ({covered / total:.0%})")
    for source, number in connection.execute(
            """select coalesce(ncm_source, 'none') source, count(*) n from silver_products
               group by 1 order by n desc"""):
        print(f"  {source:<8} {number:>5}")


# --------------------------------------------------------------------------- unmapped


def fill_unmapped_ncm(workers: int = 4, limit: Optional[int] = None) -> int:
    """Code the products neither map can reach: no Cosmos leaf (the tree has no node for fruit,
    diapers, rubbish bags...) and no barcode answer. The model reads the name and picks from the
    official table, with the same propose/repair as the category map.
    """
    from warehouse.ncm_draft import Drafter

    db.init()
    table = ncm.Table.load()
    connection = db.connect()
    try:
        rows = connection.execute(
            """select canonical_product_key, display_name, raw_brand from silver_products
               where ncm_code is null""").fetchall()
        if limit:
            rows = rows[:limit]
        if not rows:
            print("every product already has a code")
            return 0
        drafter = Drafter(table, workers=workers)
        if not drafter.ready:
            print("OLLAMA_API_KEY is empty: cannot code the products without a category", file=sys.stderr)
            return 2
        texts = [f'{row["display_name"]} {row["raw_brand"] or ""}'.strip() for row in rows]
        updates = []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for row, draft in zip(rows, pool.map(drafter.for_text, texts)):
                if draft is None:
                    continue
                updates.append((draft.code, round(draft.confidence, 3), now(),
                                row["canonical_product_key"]))
        connection.executemany(
            """update silver_products
                  set ncm_code=?, ncm_source='product', ncm_confidence=?, ncm_updated_at=?
                where canonical_product_key=?""", updates)
        ncm.apply_product_overrides(connection, table=table)
        connection.commit()
        print(f"coded {len(updates)}/{len(rows)} product(s) from their name")
        report_ncm(connection)
        return 0
    finally:
        connection.close()


# --------------------------------------------------------------------------- unmapped


def classify_unmapped(workers: int = 4, limit: Optional[int] = None) -> int:
    """Classify the products that have no leaf, then give them their NCM.

    Products that only ever arrived through a published snapshot were classified against whatever
    taxonomy was loaded then; when it was the food-only one they were parked in ``fora-da-taxonomia``
    and the market.db pass never sees them again. This re-asks the model with the current taxonomy.
    """
    db.init()
    taxonomy = Taxonomy.load()
    table = ncm.Table.load()
    category_codes = ncm.read_category_map(table=table)
    connection = db.connect()
    try:
        leaves = {node.slug for node in taxonomy.leaves}
        rows = [row for row in connection.execute(
            "select canonical_product_key, raw_name, raw_brand, category_slug from silver_products")
            if not row["category_slug"] or row["category_slug"] not in leaves]
        if limit:
            rows = rows[:limit]
        if not rows:
            print("every product already has a leaf")
            return 0
        items = [{"id": index, "name": row["raw_name"], "brand": row["raw_brand"]}
                 for index, row in enumerate(rows)]
        results = classify(items, taxonomy, workers=workers)
        written = 0
        gtin_codes = ncm.answers(connection)
        for index, row in enumerate(rows):
            result = results.get(index)
            if result is None or not result.slug:
                continue
            gtin = connection.execute(
                "select gtin from silver_products where canonical_product_key=?",
                (row["canonical_product_key"],)).fetchone()[0]
            answer = ncm.resolve(result.slug, gtin, category_codes, gtin_codes)
            connection.execute(
                """update silver_products
                      set category_slug=?, category_path=?, category_source=?, category_confidence=?,
                          review_status=?, updated_at=?,
                          ncm_code=?, ncm_source=?, ncm_confidence=?, ncm_updated_at=?
                    where canonical_product_key=?""",
                (result.slug, result.path, result.source, result.confidence,
                 "pending" if result.confidence < 0.7 else "none", now(),
                 answer.code if answer else None, answer.source if answer else None,
                 answer.confidence if answer else None, now() if answer else None,
                 row["canonical_product_key"]))
            written += 1
        connection.commit()
        print(f"classified {written}/{len(rows)} product(s) that had no leaf")
        report_ncm(connection)
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
        total_codes = connection.execute("select count(*) from dim_ncm").fetchone()[0]
        mapped_leaves = connection.execute("select count(*) from map_category_ncm").fetchone()[0]
        print(f"ncm:             {total_codes} codes, {mapped_leaves} category code(s), "
              f"{connection.execute('select count(*) from map_gtin_ncm').fetchone()[0]} barcode answer(s)")
        print("\nby category:")
        for row in connection.execute(
                """select category_slug, count(*) n from silver_products
                   group by category_slug order by n desc limit 15"""):
            print(f"  {row['category_slug']:<40} {row['n']:>5}")
    finally:
        connection.close()
    return 0
