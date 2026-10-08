import { z } from "zod";
import type { ReceiptResult } from "./receipt";

/**
 * Whether the receipt check is offered. POST /api/receipt/ocr exists only in the local Flask API
 * (scraping/local_api/app.py, which needs OpenCV and a provider key); the production Worker has no host for
 * it yet and answers 501. So it shows in development, and a production build opts in with
 * VITE_RECEIPT_OCR=1 once there is somewhere for it to run.
 */
export const receiptOcrEnabled = import.meta.env.DEV || import.meta.env.VITE_RECEIPT_OCR === "1";

/** The server refuses more than this; checking first spares an upload that can only fail. */
export const RECEIPT_MAX_BYTES = 10 * 1024 * 1024;
/** What the server can decode (an iPhone's HEIC, for one, it cannot). */
export const RECEIPT_TYPES = ["image/jpeg", "image/png", "image/webp"];
/** Reading takes three provider calls in parallel, each of which may retry once: a minute is normal. */
const TIMEOUT_MS = 150_000;

export type ReceiptFailure = "invalid" | "busy" | "unavailable" | "network" | "timeout" | "format";

export class ReceiptError extends Error {
  constructor(
    message: string,
    readonly kind: ReceiptFailure,
    /** Seconds the server asked to wait before trying again (429), when it said. */
    readonly retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ReceiptError";
  }
}

/** Why a file cannot be a receipt photo, in words for the screen, or null when it can. */
export function receiptFileProblem(file: Pick<File, "type" | "size">): string | null {
  if (!RECEIPT_TYPES.includes(file.type))
    return "Envie uma foto em JPEG, PNG ou WebP. Se ela veio do iPhone em outro formato, tire a foto de novo ou exporte como JPEG.";
  if (file.size > RECEIPT_MAX_BYTES) return "A foto é grande demais (máximo 10 MB). Tire de novo em uma resolução menor.";
  if (file.size === 0) return "O arquivo está vazio.";
  return null;
}

const reais = z.number().nullable();
const lineSchema = z.object({
  line_no: z.number().int().nullable(),
  name: z.string(),
  qty: reais,
  unit: z.string().nullable(),
  unit_price: reais,
  discount: reais,
  total: reais,
  printed_total: reais,
  contested: z.boolean(),
});
const receiptSchema = z.object({
  items: z.array(lineSchema),
  flags: z.object({
    bad_math: z.array(z.number()),
    missing_lines: z.array(z.number()),
    duplicate_lines: z.array(z.number()),
  }),
  failed_tiles: z.array(z.number()),
  degraded: z.boolean(),
});

const isTimeout = (error: unknown) => (error as { name?: string } | null)?.name === "TimeoutError";

/** The server's own message when it is a short string of ours to show, else the fallback. */
function serverMessage(body: unknown, fallback: string): string {
  const message = (body as { error?: unknown } | null)?.error;
  return typeof message === "string" && message.trim() && message.length <= 200 ? message : fallback;
}

/**
 * POST /api/receipt/ocr: a photo in, the lines read from it out. Never throws anything but a
 * {@link ReceiptError} (a cancellation passes through, since it is not a failure to show). The server's
 * messages are already in Portuguese and say what to do ("máximo 10 MB", "tente de novo em instantes").
 */
export async function readReceipt(file: File, signal?: AbortSignal, url = "/api/receipt/ocr"): Promise<ReceiptResult> {
  const form = new FormData();
  form.append("image", file);
  const combined = signal ? AbortSignal.any([signal, AbortSignal.timeout(TIMEOUT_MS)]) : AbortSignal.timeout(TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(url, { method: "POST", body: form, signal: combined });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (isTimeout(error)) throw new ReceiptError("A leitura do cupom demorou mais que o esperado. Tente de novo.", "timeout");
    throw new ReceiptError("Não foi possível enviar o cupom. Verifique sua conexão e tente de novo.", "network");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 400 || response.status === 413)
      throw new ReceiptError(serverMessage(body, "Não foi possível ler essa foto. Tente com outra."), "invalid");
    if (response.status === 429) {
      const wait = Number(response.headers.get("retry-after"));
      const known = Number.isFinite(wait) && wait > 0;
      // The server's own text says "em instantes"; when it also said how long, that exact wait replaces it.
      throw new ReceiptError(
        known ? `Muitas leituras agora. Tente de novo em ${Math.ceil(wait)} s.` : serverMessage(body, "Muitas leituras agora. Tente de novo em instantes."),
        "busy",
        known ? wait : null,
      );
    }
    // 404/501 (no host for it in this build), 503 (not installed / no key), 502 (the provider): all "not now".
    throw new ReceiptError(serverMessage(body, "A leitura de cupons não está disponível agora."), "unavailable");
  }
  let json: unknown;
  try {
    json = await response.json();
  } catch (error) {
    if (signal?.aborted) throw error;
    if (isTimeout(error)) throw new ReceiptError("A leitura do cupom demorou mais que o esperado. Tente de novo.", "timeout");
    throw new ReceiptError("A resposta da leitura do cupom veio incompleta. Tente de novo.", "format");
  }
  const parsed = receiptSchema.safeParse(json);
  if (!parsed.success) throw new ReceiptError("A resposta da leitura do cupom veio incompleta. Tente de novo.", "format");
  return parsed.data;
}
