import postgres from "postgres";

export type SnapshotMeta = { etag: string; generatedAt: string };
export type Snapshot = SnapshotMeta & { payload: string };
/** One price a product was seen at in a chain (the cloud database's price_points, see scraping/db/schema.sql). */
export type PricePoint = { key: string; store: string; observedAt: string; priceCents: number };

/** Where published snapshots are read from. The Python publisher writes them (see db/schema.sql). */
export interface SnapshotStore {
  /** Etag and time of the newest snapshot, without its (large) payload. */
  latestMeta(): Promise<SnapshotMeta | null>;
  latest(): Promise<Snapshot | null>;
  /** The price points of these products (keys from the offers' price_key), oldest first. */
  priceHistory(keys: string[]): Promise<PricePoint[]>;
}

type Row = { etag: string; generated_at: Date; payload?: string };
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
  };
}
