# Pipeline Review: receipt upload → queue → worker → completed

Reviewed at 23b83ad (same tree as origin/main e233db5, 2026-09-17).

Scope: `POST /api/receipts/scan` and the Telegram bot as the two entry points, through the
Postgres queue, the worker, OCR / model / heuristic extraction, matching, and the `completed`
receipt the review screen reads. Confirm (`POST /receipts/{id}/confirm`) is the next review.

## Flow
api/endpoints/receipts.py:upload_receipt → services/receipt_ingest.py:ingest_receipt_file
→ crud/receipt.py:create_receipt (file to `data/receipts/`, row) → services/receipt_queue.py:enqueue
→ worker/receipt_worker.py:run_once → receipt_queue.py:fail_stale, claim_next
→ services/receipt_processing.py:process_receipt → _read_receipt
  → ocr_service.py:extract_text_from_receipt (pdfplumber | MinerU)
  → llm_extractor.py:extract_from_text | extract_from_image → parse_completion
  → parsers/heuristic.py:parse_receipt_text (fallback)
→ matching_service.py:match_line per line, non_food.py:known_non_food
→ receipt row: ocr_structured, status `completed` → broadcast_receipt_status
→ schemas/receipt.py:ReceiptResponse.derive_items (what the review screen and the bot read)

Telegram: telegram_bot/handlers.py:_receive → the same ingest_receipt_file; notifier.py polls the row.

## Critical (must fix)
None found.

## Important (should fix)
- [ ] backend/app/services/receipt_processing.py:110-115, 172-180 and
      backend/app/api/endpoints/receipts.py:183-194 — **An image-only PDF completes with zero
      items and cannot be re-read.** A PDF goes straight to `_read_text` with whatever
      pdfplumber found; a scanned PDF (iOS Notes / Files "Scan Documents", a scanner app, a
      photo printed to PDF) has no text layer, so the model is called with an empty receipt,
      answers `p: []`, the heuristic parser also finds nothing, and the receipt is stored
      `completed`, method `text`, 0 lines, no `fallback_reason`. MinerU is never tried even
      though its `file_parse` endpoint takes PDFs. `/process` then refuses with 409 "already
      read" because only heuristic receipts may be re-queued, so the only way out is to delete
      the receipt and re-upload it as an image. Fix: when PDF text is blank, treat the PDF like
      an image (OCR, then vision), and let `/process` re-read a completed receipt with zero
      lines.
- [ ] backend/app/services/receipt_ingest.py:286, backend/app/crud/receipt.py:102-103,
      backend/app/services/ocr_service.py:53-56, backend/app/telegram_bot/handlers.py:152-155
      — **Ingest accepts on content type; the worker routes on the filename extension.** A
      Telegram document with `mime_type` `application/pdf` or `image/jpeg` but no `file_name`
      (the Bot API field is optional) is named `telegram-<id>` with no suffix, is accepted, the
      user is told "received, n ahead", and the worker then fails it with
      `Unsupported file type:` because neither `is_pdf` nor `IMAGE_SUFFIXES` matches. The API
      path has the same gap (`file.filename or "receipt"` at receipts.py:63) though the iPad
      file input always supplies a name. Fix: derive the stored extension from the validated
      content type, not from the client's filename.

## Minor
- [ ] backend/app/crud/receipt.py:106-128 — The file is written to disk before the row is
      inserted. When the insert fails (the concurrent-duplicate `IntegrityError` that
      receipt_ingest.py:307 handles, or any commit error) `data/receipts/<uuid>.<ext>` stays
      behind with no row pointing at it.
- [ ] backend/app/api/endpoints/receipts.py:62 and backend/app/services/llm_extractor.py:329
      — No size cap on the API upload path; `await file.read()` loads the whole body and, when
      MinerU is down, the full image is base64-encoded into one JSON request to the gateway.
      The Telegram path caps at 20 MB (client.py:11). A multi-shot iPad photo is a few MB, so
      this only bites with an oversized share, but it fails late (in the worker) rather than at
      upload.
- [ ] backend/app/api/endpoints/receipts.py:103,136 and
      backend/app/services/receipt_queue.py:445-463 — `fail_stale` issues an UPDATE and a
      COMMIT on every `GET /receipts` and `GET /receipts/{id}`. The iPad polls both, so idle
      polling is a steady stream of write transactions. Harmless at one household; move the
      stale check to the worker loop only (it already runs there, line 566) if it ever shows
      up in Postgres logs.
- [ ] backend/app/services/llm_extractor.py:108 — The known-products list offered to the model
      is sorted alphabetically and then cut at 300. Once the catalog passes 300 generic names,
      products late in the alphabet (Tomato, Yoghurt) are never offered, the model coins its own
      spelling, and reuse depends on fuzzy matching at ≥ 80.

## Verified sound
- Duplicate uploads: SHA-256 unique index plus the `IntegrityError` re-read handle two
  concurrent uploads of the same bytes from two API workers or the bot (receipt_ingest.py:292-313).
- Queue claim is atomic: `UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED LIMIT 1)` in one
  transaction (receipt_queue.py:415-435), so a second worker cannot take the same receipt.
- Every failure path ends in `failed` with a stored reason: `process_receipt` catches
  everything, rolls back and re-marks; the worker's outer handler covers a failing handler;
  stale detection covers a dead worker. Worst-case processing (MinerU 120 s + model 180 s)
  stays under the 10-minute stale limit.
- Truncated model output cannot be stored as a partial receipt: the `{…}` slice of a cut-off
  array is invalid JSON, so it raises and falls back to the heuristic parser
  (llm_extractor.py:169-183).
- Category ids are matched case-insensitively and `household` is kept as a non-food sentinel,
  never a category (llm_extractor.py:212-224).
- Store chain: the value given at upload wins, and processing and confirm normalise it the
  same way (receipt_processing.py:210-212, receipt_confirm.py:79).
- Broadcasts happen after commit, and a Redis failure is logged and swallowed, so the receipt
  state never depends on Redis.
- API, worker and bot all mount `kyokki_data` at `/app/data` with `WORKDIR /app`, so the
  relative `image_path` resolves to the same file in every container.
- Nothing on this path logs receipt text, images, prompts or the API key at INFO.
