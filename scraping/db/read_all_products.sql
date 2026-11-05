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
-- stores.name is the chain (stores.chain is a legacy column that is always empty), and prices holds one
-- row per product and store that is updated in place, so "latest" is just the row - the window function
-- only guards against a duplicate a concurrent scrape could have left behind.
--
-- SELECT p.id, p.name, p.brand, p.category, p.gtin, p.image_url,
--        latest.store, latest.price, latest.regular_price, latest.offer, latest.scraped_at
-- FROM products p
-- LEFT JOIN (
--     SELECT pr.product_id, s.name AS store, pr.price, pr.regular_price, pr.offer, pr.scraped_at,
--            ROW_NUMBER() OVER (PARTITION BY pr.product_id, pr.store_id
--                               ORDER BY pr.scraped_at DESC, pr.id DESC) AS rn
--     FROM prices pr
--     JOIN stores s ON s.id = pr.store_id
-- ) latest ON latest.product_id = p.id AND latest.rn = 1
-- ORDER BY p.name, latest.store;
