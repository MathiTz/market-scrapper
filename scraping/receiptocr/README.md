# receiptocr

OCR extraction library for Brazilian NFC-e supermarket receipts using overlapping zoomed horizontal tiles and consensus voting without LLM arithmetic.

## How it works

The image is split into 3 overlapping horizontal bands (2× Lanczos zoom). Each
band is sent in parallel to the Ollama cloud API with a transcribe-only
prompt: the model must copy printed digits literally — **it never computes,
corrects, or verifies any number**. All arithmetic (line totals, discount
normalization, math checks) happens in Python. Readings from overlapping
regions are merged by receipt line number with weighted majority voting;
the printed line total is the authoritative charged amount.

## Installation

```bash
pip install .
```

Requires `OLLAMA_API_KEY` in the environment (or a `.env` file in the
working directory, or pass `api_key=`).

## CLI Usage

```bash
python -m receiptocr photos/receipt.jpeg          # item table + flags
python -m receiptocr photos/receipt.jpeg --json   # full JSON document
```

Exit codes: 0 ok · 1 usage/bad request · 3 auth/quota · 4 provider issues.

## Python API

```python
from receiptocr import ReceiptExtractor

extractor = ReceiptExtractor()
receipt = extractor.extract("photos/receipt.jpeg")

for item in receipt.items:
    print(f"{item.line_no}: {item.name} - R$ {item.total:.2f}")

if not receipt.flags.ok:
    print("suspicious lines:", receipt.flags.bad_math,
          "missing:", receipt.flags.missing_lines)
if receipt.degraded:
    print("tiles failed:", receipt.failed_tiles, "- quality may be reduced")
```

## Error handling

All errors derive from `ReceiptOcrError`:

- `AuthenticationError` (401/403), `QuotaError` (402, out of credits),
  `ModelNotFoundError` (404), `BadRequestError` (400/413/422) — **not
  retried**: fix configuration or credits, then retry.
- `RateLimitedError` (429, honors `retry-after`, sleeps capped at 30 s),
  `ProviderUnavailableError` (5xx, connection, DNS, TLS), `BadReplyError`
  (HTTP 200 with empty/garbage content) — retried once, then raised.
- If every tile fails: `ReceiptOcrError`. If only some tiles fail, you get a
  **degraded** `Receipt` — check `receipt.degraded` / `receipt.failed_tiles`.

## Design notes

- **Name selection prefers the shortest similar reading**: on degraded
  prints, longer names are empirically more hallucinated (models append
  fragments like "1 un" or invent word tails); the benchmark data showed
  shortest-of-similar is the most faithful transcription.
- A printed+math-consistent total outranks a bare majority when they
  disagree: the printed total is what the register charged.
- `receipt.raw` keeps the per-tile parsed items for debugging.