import postgres from "postgres";

export type SnapshotMeta = { etag: string; generatedAt: string };
export type Snapshot = SnapshotMeta & { payload: string };
/** One price a product was seen at in a chain (the cloud database's price_points, see scraping/db/schema.sql). */
export type PricePoint = { key: string; store: string; observedAt: string; priceCents: number };

/** One chain's current price of a product (the cloud database's current_prices). */
export type CataloguePrice = {
  store: string;
  price_cents: number;
  regular_price_cents: number | null;
  deal_label: string | null;
  source_url: string | null;
  observed_at: string;
  stock: number | null;
};
/** A product with every chain's current price; the same body scraping/services/catalogue_search.py answers. */
export type CatalogueItem = {
  key: string;
  name: string;
  brand: string;
  category: string;
  subcategory: string;
  amount: number;
  unit: string;
  pack_count: number;
  gtin: string | null;
  image_url: string | null;
  prices: CataloguePrice[];
};
export type CatalogueResult = { results: CatalogueItem[]; truncated: boolean };

/** Where published snapshots are read from. The Python publisher writes them (see db/schema.sql). */
export interface SnapshotStore {
  /** Etag and time of the newest snapshot, without its (large) payload. */
  latestMeta(): Promise<SnapshotMeta | null>;
  latest(): Promise<Snapshot | null>;
  /** The price points of these products (keys from the offers' price_key), oldest first. */
  priceHistory(keys: string[]): Promise<PricePoint[]>;
  /** The products anyone lists right now whose name or brand starts with each of ``words`` (see ./search.ts). */
  searchCatalogue(words: string[], limit: number): Promise<CatalogueResult>;
}

type Row = { etag: string; generated_at: Date; payload?: string };
type HitRow = Omit<CatalogueItem, "prices" | "key"> & { product_key: string };
type ListingRow = Omit<CataloguePrice, "observed_at"> & { product_key: string; observed_at: Date };
// Accented letters to their plain ones, so a search ignores accents without needing the unaccent extension.
const ACCENTED = "áàâãäéèêëíìîïóòôõöúùûüç";
const PLAIN = "aaaaaeeeeiiiiooooouuuuc";
type PointRow = { product_key: string; store: string; observed_at: Date; price_cents: number };

/** Reads snapshots from Postgres (through Hyperdrive on Cloudflare). One short-lived client per call. */
export function postgresStore(connectionString: string): SnapshotStore {
  async function query<T>(run: (sql: postgres.Sql) => Promise<T>): Promise<T> {
    // No prepared statements: they do not survive a pooler (Hyperdrive, Neon's pgbouncer) in between.
    const sql = postgres(connectionString, { max: 1, fetch_types: false, prepare: false });
    try {
      return await run(sql);
    } finally {
      await sql.end({ timeout: 1 });
    }
  }
  return {
    async latestMeta() {
      const [row] = await query((sql) =>
        sql<Row[]>`SELECT etag, generated_at FROM snapshots ORDER BY id DESC LIMIT 1`,
      );
      return row ? { etag: row.etag, generatedAt: row.generated_at.toISOString() } : null;
    },
    async latest() {
      const [row] = await query((sql) =>
        sql<Row[]>`SELECT etag, generated_at, payload FROM snapshots ORDER BY id DESC LIMIT 1`,
      );
      return row
        ? { etag: row.etag, generatedAt: row.generated_at.toISOString(), payload: row.payload! }
        : null;
    },
    async priceHistory(keys) {
      const rows = await query((sql) =>
        sql<PointRow[]>`
          SELECT product_key, store, observed_at, price_cents FROM price_points
          WHERE product_key IN ${sql(keys)} ORDER BY product_key, store, observed_at`,
      );
      return rows.map((r) => ({
        key: r.product_key,
        store: r.store,
        observedAt: r.observed_at.toISOString(),
        priceCents: r.price_cents,
      }));
    },
    async searchCatalogue(words, limit) {
      return query(async (sql) => {
        const plain = (column: postgres.PendingQuery<postgres.Row[]>) =>
          sql`translate(lower(${column}), ${ACCENTED}, ${PLAIN})`;
        const text = plain(sql`p.name || ' ' || coalesce(p.brand, '')`);
        // Each word was reduced to [a-z0-9] by wordsOf, so it is safe inside the pattern.
        const matches = words
          .map((word) => sql`${text} ~ ${`(^|[^a-z0-9])${word}`}`)
          .reduce((all, one) => sql`${all} AND ${one}`);
        const hits = await sql<HitRow[]>`
          SELECT p.product_key, p.brand, p.category, p.subcategory, p.amount, p.unit, p.pack_count, p.gtin, p.image_url,
                 (SELECT min(c.display_name) FROM current_prices c WHERE c.product_key = p.product_key) AS name
          FROM products p
          WHERE EXISTS (SELECT 1 FROM current_prices c WHERE c.product_key = p.product_key) AND ${matches}
          ORDER BY (${plain(sql`p.name`)} LIKE ${words[0] + "%"}) DESC, length(p.name), p.name
          LIMIT ${limit + 1}`;
        const shown = hits.slice(0, limit);
        const keys = shown.map((h) => h.product_key);
        const listings = keys.length
          ? await sql<ListingRow[]>`
              SELECT product_key, store, price_cents, regular_price_cents, deal_label, source_url, observed_at, stock
              FROM current_prices WHERE product_key IN ${sql(keys)} ORDER BY product_key, store`
          : [];
        const prices = new Map<string, CataloguePrice[]>();
        for (const { product_key, observed_at, ...rest } of listings) {
          const list = prices.get(product_key) ?? [];
          list.push({ ...rest, observed_at: observed_at.toISOString() });
          prices.set(product_key, list);
        }
        return {
          results: shown.map(({ product_key, ...rest }) => ({
            ...rest,
            key: product_key,
            brand: rest.brand ?? "",
            prices: prices.get(product_key) ?? [],
          })),
          truncated: hits.length > limit,
        };
      });
    },
  };
}
