/** Why the offers could not be loaded, in terms a shopper can act on (never the raw technical error). */
export type LoadFailure = "unavailable" | "network" | "timeout" | "format";

export class LoadError extends Error {
  constructor(
    message: string,
    readonly kind: LoadFailure,
  ) {
    super(message);
    this.name = "LoadError";
  }
}

const TIMEOUT_MS = 15000;

const isTimeout = (error: unknown) => (error as { name?: string } | null)?.name === "TimeoutError";

/**
 * GET /api/public: the whole published snapshot, which the UI then searches and filters itself. A failure
 * becomes a {@link LoadError} with a message fit for the screen; a cancellation by React Query (a newer
 * request replaced this one) is passed through untouched, since it is not an error to show.
 */
export async function loadSnapshot<T>(signal: AbortSignal, url = "/api/public"): Promise<T> {
  const combined = AbortSignal.any([signal, AbortSignal.timeout(TIMEOUT_MS)]);
  let response: Response;
  try {
    response = await fetch(url, { signal: combined });
  } catch (error) {
    if (signal.aborted) throw error;
    if (isTimeout(error)) throw new LoadError("A consulta das ofertas demorou mais que o esperado.", "timeout");
    throw new LoadError("Não foi possível conectar ao serviço de ofertas.", "network");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      typeof body?.error === "string" && body.error.trim() && body.error.length <= 200
        ? body.error
        : "O serviço de ofertas não respondeu como esperado.";
    throw new LoadError(message, "unavailable");
  }
  try {
    return (await response.json()) as T;
  } catch (error) {
    if (signal.aborted) throw error;
    if (isTimeout(error)) throw new LoadError("A consulta das ofertas demorou mais que o esperado.", "timeout");
    throw new LoadError("Os dados recebidos das ofertas estão incompletos.", "format");
  }
}

/** The message for any error thrown while loading (a LoadError's own, or a generic one). */
export function loadErrorMessage(error: unknown): string {
  return error instanceof LoadError ? error.message : "Não foi possível carregar as ofertas agora.";
}
