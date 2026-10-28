"""Snapshot-driven ingestion: the online database publishes, this consumes.

The flow the project needs:

    new snapshot in Postgres
        -> detect it (etag/id watermark)
        -> capture the new products and every offer as a price observation
        -> fetch images only for products still missing one
        -> classify only the products never seen before
        -> done: the warehouse is up to date

Every step is idempotent. Re-reading a snapshot is a no-op, an offer already recorded is ignored by
its unique key, an image already mirrored is skipped, and a classified product is never re-sent to
the model. That is what makes each run find fewer new items than the last.

    python -m warehouse_snapshot --file /tmp/snapshot.json
    python -m warehouse_snapshot --dsn "$PUBLISH_DATABASE_URL"
    python -m warehouse_snapshot --status
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple


from config import BASE_DIR
from services import image_mirror
from services.public_api import clean, display_name, match_tokens, parse_size
from warehouse import config, db
from warehouse.classifier import path_of, signature
from warehouse.etl import (cache, canonical_key, classify, normalize_gtin, now, seed_brands)
from warehouse.taxonomy import Taxonomy

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- reading the snapshot


def read_file(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return {
        "key": int(digest[:12], 16),
        "etag": data.get("etag") or digest,
        "generated_at": data.get("generated_at") or now(),
        "sha256": digest,
        "data": data,
        "source": "file",
    }


def read_postgres(dsn: str, snapshot_id: Optional[int] = None) -> Optional[dict]:
    """The newest published snapshot (or a specific one). Read-only."""
    import psycopg

    with psycopg.connect(dsn) as connection:
        query = "select id, etag, generated_at, payload from snapshots"
        params: tuple = ()
        if snapshot_id is None:
            query += " order by id desc limit 1"
        else:
            query += " where id = %s"
            params = (snapshot_id,)
        row = connection.execute(query, params).fetchone()
    if row is None:
        return None
    key, etag, generated_at, payload = row
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return {
        "key": int(key),
        "etag": etag,
        "generated_at": generated_at.isoformat() if hasattr(generated_at, "isoformat") else str(generated_at),
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "data": json.loads(raw),
        "source": "postgres",
    }


# --------------------------------------------------------------------------- warehouse rows


def _already_ingested(connection, etag: str) -> bool:
    return connection.execute(
        "select 1 from bronze_snapshots where etag=?", (etag,)).fetchone() is not None


def _store_image(connection, key: str, candidate, status: str, decision: Optional[dict]) -> None:
    webp, width, height = candidate.prepared
    digest = hashlib.sha256(webp).hexdigest()
    relative = Path("images") / digest[:2] / f"{digest}.webp"
    absolute = Path(BASE_DIR) / relative
    try:
        absolute.parent.mkdir(parents=True, exist_ok=True)
        if not absolute.exists():
            absolute.write_bytes(webp)
    except OSError as exc:
        logger.error("could not write %s: %s", absolute, exc)
    connection.execute(
        """insert into warehouse_images
             (product_key, sha256, path, width, height, bytes, source_kind, source_url, status, decision, checked_at)
           values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           on conflict(product_key) do update set
             sha256=excluded.sha256, path=excluded.path, width=excluded.width, height=excluded.height,
             bytes=excluded.bytes, source_kind=excluded.source_kind, source_url=excluded.source_url,
             status=excluded.status, decision=excluded.decision, checked_at=excluded.checked_at""",
        (key, digest, str(relative), width, height, len(webp), candidate.kind,
         candidate.source_url, status, json.dumps(decision, ensure_ascii=False) if decision else None, now()))


def _seed_images_from_market(connection, products: List[dict]) -> int:
    """Reuse images already mirrored for market.db instead of downloading them again.

    The snapshot's product ids come from market.db, so ``product_images`` (the image mirror) and the
    warehouse point at the same products. Copying the rows turns the first snapshot ingestion from
    thousands of downloads into a table copy.
    """
    import sqlite3

    source = db.source_market()
    try:
        rows = {}
        for row in source.execute(
                """select p.name, p.gtin, i.* from product_images i
                   join products p on p.id = i.product_id"""):
            rows[canonical_key({"name": row["name"], "gtin": row["gtin"]})] = dict(row)
    except sqlite3.OperationalError:
        return 0
    finally:
        source.close()
    seeded = 0
    for product in products:
        key = canonical_key(product)
        row = rows.get(key)
        if not row:
            continue
        if connection.execute("select 1 from warehouse_images where product_key=?", (key,)).fetchone():
            continue
        connection.execute(
            """insert into warehouse_images
                 (product_key, sha256, path, width, height, bytes, source_kind, source_url, status, decision, checked_at)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, row["sha256"], row["path"], row["width"], row["height"], row["bytes"],
             row["source_kind"], row["source_url"], row["status"], row["decision"], now()))
        seeded += 1
    return seeded


def _fetch_image(product: dict, key: str) -> Tuple[Optional[object], Optional[dict], str]:
    """Chain URL first (trusted), then the lookup ladder with the decision model as a gate."""
    http = image_mirror._http()
    view = SimpleNamespace(id=product.get("id"), name=product["name"], brand=product.get("brand"),
                           gtin=product.get("gtin"), image_url=product.get("image_url"))
    blob = image_mirror.fetch_bytes(view.image_url, http) if view.image_url else None
    ready = image_mirror.prepare(blob) if blob else None
    if ready:
        return image_mirror.Candidate("snapshot", view.image_url, blob, ready), None, "ok"

    tried = 0
    first = None
    for source in (image_mirror.openfoodfacts_candidates, image_mirror.chain_search_candidates,
                   image_mirror.web_search_candidates):
        for candidate in source(view, http):
            first = first or candidate
            tried += 1
            accepted, evidence = image_mirror.verify(view, candidate.prepared[0])
            if accepted:
                return candidate, evidence, "ok"
            if tried >= image_mirror.MAX_WEB_CANDIDATES:
                break
        if tried >= image_mirror.MAX_WEB_CANDIDATES:
            break
    if first is not None:
        return first, {"result": "flagged", "candidates": tried}, "flagged"
    return None, None, "flagged"


# --------------------------------------------------------------------------- ingestion


def ingest(snapshot: dict, limit: Optional[int] = None, with_images: bool = True,
           workers: int = 4) -> dict:
    db.init()
    taxonomy = Taxonomy.load()
    connection = db.connect()
    report = {"snapshot": snapshot["key"], "new_products": 0, "offers": 0, "images": 0,
              "classified": 0, "skipped": False}
    try:
        already = _already_ingested(connection, snapshot["etag"])
        report["skipped"] = already
        if already:
            print(f"snapshot {snapshot['key']} already ingested (etag {snapshot['etag'][:12]}); "
                  f"finishing anything still missing")

        data = snapshot["data"]
        products = data.get("products") or []
        offers = data.get("offers") or []
        if not already:
            connection.execute(
                """insert or replace into bronze_snapshots
                     (snapshot_key, etag, generated_at, payload_sha256, product_count, offer_count, source)
                   values (?, ?, ?, ?, ?, ?, ?)""",
                (snapshot["key"], snapshot["etag"], snapshot["generated_at"], snapshot["sha256"],
                 len(products), len(offers), snapshot["source"]))

        known = {row[0] for row in connection.execute("select canonical_product_key from silver_products")}
        new_products: List[dict] = []
        seed_brands(connection, products)

        for product in products:
            key = canonical_key(product)
            if key not in known:
                new_products.append({**product, "_key": key})
                known.add(key)

        # Upsert every product, preserving the classification when it already exists.
        for product in products:
            key = canonical_key(product)
            amount, unit, pack = parse_size(product["name"])
            connection.execute(
                """insert into silver_products
                     (source_product_id, raw_name, display_name, raw_brand, gtin, identity_tokens_json,
                      amount, unit, pack_count, total_base_amount, is_variable_weight,
                      canonical_product_key, image_url, last_snapshot_key, last_seen_at, updated_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   on conflict(canonical_product_key) do update set
                     source_product_id=excluded.source_product_id,
                     raw_name=excluded.raw_name, display_name=excluded.display_name,
                     raw_brand=excluded.raw_brand, gtin=excluded.gtin,
                     identity_tokens_json=excluded.identity_tokens_json,
                     amount=excluded.amount, unit=excluded.unit, pack_count=excluded.pack_count,
                     total_base_amount=excluded.total_base_amount,
                     is_variable_weight=excluded.is_variable_weight,
                     canonical_product_key=excluded.canonical_product_key,
                     image_url=excluded.image_url,
                     last_snapshot_key=excluded.last_snapshot_key,
                     last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at""",
                (int(product["id"]), product["name"], display_name(product["name"]),
                 product.get("brand") or None, normalize_gtin(product.get("gtin")),
                 json.dumps(sorted(match_tokens(product["name"]))), amount, unit, pack, amount * pack,
                 1 if unit == "g" and amount == 1000 and " kg" in f" {clean(product['name'])}" else 0,
                 key, product.get("image_url"), snapshot["key"], now(), now()))

        if not already:
            for offer in offers:
                product = next((p for p in products if str(p["id"]) == str(offer.get("product_id"))), None)
                if product is None:
                    continue
                cursor = connection.execute(
                    """insert or ignore into fact_price_observation
                         (snapshot_key, product_key, source_product_id, observed_at_iso, store_name, retailer_id,
                          price_cents, regular_price_cents, offer_label, stock, source_url)
                       values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (snapshot["key"], canonical_key(product), int(product["id"]),
                     offer.get("price_observed_at") or snapshot["generated_at"],
                     offer.get("retailer_name") or "", str(offer.get("retailer_id") or ""),
                     int(offer.get("price_cents") or 0), offer.get("regular_price_cents"),
                     offer.get("deal_label"), offer.get("stock"), offer.get("source_url")))
                report["offers"] += cursor.rowcount if cursor.rowcount > 0 else 1
        connection.commit()

        # Images: reuse what market.db already mirrored, then look up only the rest.
        if with_images:
            seeded = _seed_images_from_market(connection, products)
            connection.commit()
            if seeded:
                print(f"  reused {seeded} image(s) from the market.db mirror")
        missing = [p for p in products if connection.execute(
            "select 1 from warehouse_images where product_key=? and status in ('ok','review')",
            (canonical_key(p),)).fetchone() is None]
        if limit:
            missing = missing[:limit]
        if with_images:
            for product in missing:
                candidate, decision, status = _fetch_image(product, canonical_key(product))
                if candidate is None:
                    connection.execute(
                        """insert into warehouse_images (product_key, status, source_kind, checked_at)
                           values (?, 'flagged', '', ?)
                           on conflict(product_key) do update set status='flagged', checked_at=excluded.checked_at""",
                        (canonical_key(product), now()))
                else:
                    _store_image(connection, canonical_key(product), candidate, status, decision)
                if status == "ok":
                    report["images"] += 1
            connection.commit()

        # Classification: only products with no label yet.
        to_classify = [p for p in products if connection.execute(
            "select 1 from silver_products where canonical_product_key=? and category_slug is not null",
            (canonical_key(p),)).fetchone() is None]
        if limit:
            to_classify = to_classify[:limit]
        if to_classify:
            # The payload carries product ids as strings; the classifier keys on ints.
            items = [{**p, "id": int(p["id"])} for p in to_classify]
            pending = []
            for product in items:
                sig = signature(product["name"], product.get("brand"))
                answer = connection.execute(
                    "select answer_json from silver_llm_cache where input_signature_hash=? and prompt_version=? and method='cloud_leaf'",
                    (sig, config.PROMPT_VERSION)).fetchone()
                pending.append({**product, "_cached": json.loads(answer[0])} if answer else product)
            fresh = [p for p in pending if "_cached" not in p]
            results = classify(fresh, taxonomy, workers=workers) if fresh else {}
            for product in pending:
                if "_cached" in product:
                    slug = product["_cached"].get("slug")
                    confidence = float(product["_cached"].get("confidence") or 0.0)
                    source = "cache"
                else:
                    result = results.get(product["id"])
                    if result is None:
                        continue
                    slug, confidence, source = result.slug, result.confidence, "cloud"
                    cache(connection, signature(product["name"], product.get("brand")),
                          config.LLM_MODEL, {"slug": slug, "confidence": confidence}, confidence)
                connection.execute(
                    """update silver_products set category_slug=?, category_path=?, category_source=?,
                         category_confidence=?, review_status=?, updated_at=?
                       where canonical_product_key=?""",
                    (slug, path_of(taxonomy, slug or ""), source, confidence,
                     "pending" if confidence < 0.7 else "none", now(), canonical_key(product)))
                report["classified"] += 1
            connection.commit()

        report["new_products"] = len(new_products)
        connection.execute(
            """insert into etl_watermarks
                 (pipeline_name, last_run_started_at, last_run_completed_at, last_status, rows_processed, notes)
               values ('snapshot', ?, ?, 'ok', ?, ?)
               on conflict(pipeline_name) do update set
                 last_run_started_at=excluded.last_run_started_at,
                 last_run_completed_at=excluded.last_run_completed_at,
                 last_status='ok', rows_processed=excluded.rows_processed, notes=excluded.notes""",
            (now(), now(), report["offers"], f"snapshot {snapshot['key']}"))
        connection.commit()
        return report
    finally:
        connection.close()


def status() -> int:
    db.init()
    connection = db.connect()
    try:
        snapshots = connection.execute("select count(*) from bronze_snapshots").fetchone()[0]
        products = connection.execute("select count(*) from silver_products").fetchone()[0]
        classified = connection.execute(
            "select count(*) from silver_products where category_slug is not null").fetchone()[0]
        images = connection.execute(
            "select count(*) from warehouse_images where status='ok'").fetchone()[0]
        offers = connection.execute("select count(*) from fact_price_observation").fetchone()[0]
        print(f"snapshots ingested: {snapshots}")
        print(f"products:           {products}")
        print(f"classified:         {classified}")
        print(f"images:             {images}")
        print(f"price observations: {offers}")
    finally:
        connection.close()
    return 0
