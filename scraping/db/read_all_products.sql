-- Every product we have, with the latest price per chain. For anyone who only needs to read the data:
-- run it as `api_reader` (see readonly_role.sql) against the Neon database.
--
-- "Latest price" is the last time that chain was seen at that price, so a product a chain stopped
-- selling keeps its old price here. To get only what is listed now, add:
--     WHERE p.last_seen > now() - interval '3 days'
-- Drop the LEFT JOIN and the pp.* columns to get just the product list.
SELECT p.product_key, p.name, p.brand, p.category, p.subcategory,
       p.amount, p.unit, p.pack_count, p.gtin, p.image_url,
       p.first_seen, p.last_seen,
       pp.store,
       pp.price_cents / 100.0         AS price,
       pp.regular_price_cents / 100.0 AS regular_price,
       pp.observed_at
FROM products p
LEFT JOIN LATERAL (
    SELECT DISTINCT ON (store) store, price_cents, regular_price_cents, observed_at
    FROM price_points
    WHERE product_key = p.product_key
    ORDER BY store, observed_at DESC
) pp ON true
ORDER BY p.name, pp.store;

-- The same from the scraper's own local SQLite file (scraping/market.db), where the tables differ:
--
-- SELECT p.id, p.name, p.brand, p.category, p.gtin, s.chain AS store,
--        pr.price, pr.regular_price, pr.offer, pr.scraped_at
-- FROM products p
-- JOIN prices pr ON pr.product_id = p.id
-- JOIN stores s ON s.id = pr.store_id
-- ORDER BY p.name, s.chain;
