import { createApp } from "./app";
import { postgresStore } from "./store";

// Cloudflare Worker entry: the UI's static files are served by the platform (see wrangler.jsonc),
// and only /api/* reaches this app.
export default createApp({ store: (env) => postgresStore(env.HYPERDRIVE.connectionString) });
