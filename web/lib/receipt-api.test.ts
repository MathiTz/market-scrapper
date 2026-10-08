import { afterEach, describe, expect, it, vi } from "vitest";
import { readReceipt, receiptFileProblem, ReceiptError, RECEIPT_MAX_BYTES } from "./receipt-api";

const photo = () => new File([new Uint8Array(10)], "cupom.png", { type: "image/png" });

const goodBody = {
  items: [
    { line_no: 1, name: "LEITE INT ITALAC 1L", qty: 2, unit: "UN", unit_price: 5.49, discount: null, total: 10.98, printed_total: 10.98, contested: false },
  ],
  flags: { bad_math: [], missing_lines: [], duplicate_lines: [] },
  failed_tiles: [],
  degraded: false,
  // what the server also sends and the UI never needs: dropped by the parse
  raw: [{ tile: 0, items: [] }],
  timings: { total_ms: 1 },
};

const respond = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers })));

afterEach(() => vi.unstubAllGlobals());

async function failure(promise: Promise<unknown>): Promise<ReceiptError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ReceiptError);
    return error as ReceiptError;
  }
  throw new Error("expected a ReceiptError");
}

describe("receiptFileProblem", () => {
  it("accepts the formats the server can decode", () => {
    for (const type of ["image/jpeg", "image/png", "image/webp"]) expect(receiptFileProblem({ type, size: 1000 })).toBeNull();
  });

  it("refuses other formats (HEIC, PDF), oversized and empty files, before anything is uploaded", () => {
    expect(receiptFileProblem({ type: "image/heic", size: 1000 })).toMatch(/JPEG/);
    expect(receiptFileProblem({ type: "application/pdf", size: 1000 })).toMatch(/JPEG/);
    expect(receiptFileProblem({ type: "image/jpeg", size: RECEIPT_MAX_BYTES + 1 })).toMatch(/10 MB/);
    expect(receiptFileProblem({ type: "image/jpeg", size: 0 })).toMatch(/vazio/);
  });
});

describe("readReceipt", () => {
  it("sends the photo as multipart under the field the server reads, and returns the parsed lines", async () => {
    respond(200, goodBody);
    const result = await readReceipt(photo());
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/receipt/ocr");
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("image")).toBeInstanceOf(File);
    expect(result.items[0].name).toBe("LEITE INT ITALAC 1L");
    expect(result.degraded).toBe(false);
    expect(result).not.toHaveProperty("raw");
  });

  it("shows the server's own message for a refused photo (400) or an oversized one (413)", async () => {
    respond(400, { error: "Envie uma imagem válida do cupom (PNG ou JPEG)." });
    expect((await failure(readReceipt(photo()))).message).toBe("Envie uma imagem válida do cupom (PNG ou JPEG).");
    respond(413, { error: "A imagem do cupom tem resolução alta demais." });
    const error = await failure(readReceipt(photo()));
    expect(error.kind).toBe("invalid");
    expect(error.message).toBe("A imagem do cupom tem resolução alta demais.");
  });

  it("tells a busy service (429) apart, with how long to wait when the server said", async () => {
    respond(429, { error: "Muitas leituras de cupom agora. Tente de novo em instantes." }, { "Retry-After": "7" });
    const error = await failure(readReceipt(photo()));
    expect(error.kind).toBe("busy");
    expect(error.retryAfter).toBe(7);
    expect(error.message).toBe("Muitas leituras agora. Tente de novo em 7 s."); // one "try again", with the exact wait

    respond(429, { error: "Muitas leituras de cupom agora. Tente de novo em instantes." }); // no Retry-After
    const unknown = await failure(readReceipt(photo()));
    expect(unknown.retryAfter).toBeNull();
    expect(unknown.message).toBe("Muitas leituras de cupom agora. Tente de novo em instantes.");
  });

  it("treats a missing route, an unconfigured server and a failing provider alike: not available now", async () => {
    for (const status of [404, 501, 503, 502]) {
      respond(status, { error: "A leitura de cupons não está configurada neste servidor." });
      const error = await failure(readReceipt(photo()));
      expect(error.kind).toBe("unavailable");
    }
  });

  it("falls back to its own message when the error body is not usable (a proxy's HTML page, a long dump)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })));
    expect((await failure(readReceipt(photo()))).message).toMatch(/não está disponível/);
    respond(502, { error: "x".repeat(500) });
    expect((await failure(readReceipt(photo()))).message).toMatch(/não está disponível/);
  });

  it("says so when the connection fails, or the reading takes too long", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect((await failure(readReceipt(photo()))).kind).toBe("network");
    const timeout = Object.assign(new Error("timed out"), { name: "TimeoutError" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(timeout));
    expect((await failure(readReceipt(photo()))).kind).toBe("timeout");
  });

  it("lets a cancellation through untouched: it is not a failure to show", async () => {
    const controller = new AbortController();
    controller.abort();
    const aborted = Object.assign(new Error("aborted"), { name: "AbortError" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(aborted));
    await expect(readReceipt(photo(), controller.signal)).rejects.toBe(aborted);
  });

  it("refuses a 200 whose body is not a receipt rather than showing a half-empty result", async () => {
    respond(200, { items: [{ name: "LEITE" }] });
    expect((await failure(readReceipt(photo()))).kind).toBe("format");
    respond(200, { not: "a receipt" });
    expect((await failure(readReceipt(photo()))).kind).toBe("format");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json", { status: 200 })));
    expect((await failure(readReceipt(photo()))).kind).toBe("format");
  });
});
