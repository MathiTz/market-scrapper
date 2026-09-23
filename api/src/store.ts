import postgres from "postgres";

export type SnapshotMeta = { etag: string; generatedAt: string };
export type Snapshot = SnapshotMeta & { payload: string };

/** Where published snapshots are read from. The Python publisher writes them (see db/schema.sql). */
export interface SnapshotStore {
  /** Etag and time of the newest snapshot, without its (large) payload. */
  latestMeta(): Promise<SnapshotMeta | null>;
  latest(): Promise<Snapshot | null>;
}

type Row = { etag: string; generated_at: Date; payload?: string };

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
  };
}
