"""Reply texts for the Telegram bot."""

from datetime import date, datetime
from uuid import uuid4

from app.schemas.receipt import ReceiptResponse
from app.telegram_bot import messages


def _receipt(lines: list[dict], **overrides) -> ReceiptResponse:
    data = {
        "id": uuid4(),
        "store_chain": "s-group",
        "purchase_date": date(2026, 1, 2),
        "image_path": "data/receipts/x.pdf",
        "batch_id": None,
        "ocr_raw_text": None,
        "content_sha256": "abc",
        "ocr_structured": {"method": "text", "lines": lines},
        "processing_status": "completed",
        "items_extracted": len(lines),
        "items_matched": sum(1 for line in lines if line.get("product_id")),
        "created_at": datetime(2026, 1, 2, 12, 0),
    }
    data.update(overrides)
    return ReceiptResponse.model_validate(data)


def _line(name: str, matched: bool = False) -> dict:
    return {
        "name": name,
        "quantity": 1,
        "weight_kg": None,
        "category": "dairy",
        "product_id": str(uuid4()) if matched else None,
        "product_name": name.title() if matched else None,
    }


class TestResultText:
    def test_summary_lists_unmatched_names_and_the_rest_as_a_count(self):
        lines = [_line(f"PRODUCT {i}") for i in range(46)] + [
            _line(f"KNOWN {i}", matched=True) for i in range(3)
        ]

        text = messages.result_text(_receipt(lines))

        assert text.startswith("S-group, 2.1.2026: 49 items, 3 matched.")
        assert (
            "New: PRODUCT 0, PRODUCT 1, PRODUCT 2, PRODUCT 3, PRODUCT 4, PRODUCT 5, PRODUCT 6, PRODUCT 7, … (+38)"
            in text
        )
        assert "KNOWN 0" not in text
        assert text.endswith("Review on the iPad.")

    def test_all_matched_has_no_new_line(self):
        text = messages.result_text(_receipt([_line("MAITO", matched=True)]))
        assert "New:" not in text
        assert "1 item, 1 matched." in text

    def test_few_unmatched_names_are_listed_without_a_count(self):
        text = messages.result_text(_receipt([_line("MAITO"), _line("LEIPÄ")]))
        assert "New: MAITO, LEIPÄ\n" in text + "\n"
        assert "(+" not in text

    def test_unknown_store_and_date(self):
        text = messages.result_text(
            _receipt([_line("MAITO")], store_chain=None, purchase_date=None)
        )
        assert text.startswith("Unknown store, date not read: 1 item, 0 matched.")

    def test_long_names_stay_under_telegram_limit(self):
        lines = [_line("X" * 500) for _ in range(40)]
        assert (
            len(messages.result_text(_receipt(lines))) <= messages.TELEGRAM_TEXT_LIMIT
        )


class TestOtherTexts:
    def test_unknown_chat_reveals_only_the_chat_id(self):
        text = messages.unknown_chat_text(-100123)
        assert "-100123" in text
        assert "TELEGRAM_ALLOWED_CHAT_IDS" in text

    def test_help_asks_for_photos_as_files(self):
        text = messages.help_text()
        assert "PDF" in text
        assert "as a file" in text

    def test_received_mentions_queue_position(self):
        assert "reading" in messages.received_text(0)
        assert "2 ahead" in messages.received_text(2)

    def test_duplicate_of_completed_receipt_repeats_the_result(self):
        receipt = _receipt([_line("MAITO")])
        text = messages.duplicate_text(receipt)
        assert text.startswith("Already received")
        assert "1 item, 0 matched" in text

    def test_duplicate_still_processing(self):
        receipt = _receipt([], processing_status="processing", ocr_structured=None)
        assert "still being read" in messages.duplicate_text(receipt)

    def test_failure_is_short(self):
        text = messages.failure_text("Receipt processing failed: " + "x" * 1000)
        assert text.startswith("Could not read this receipt")
        assert len(text) < 400

    def test_unsupported_and_too_large(self):
        assert "PDF" in messages.unsupported_text()
        assert "20 MB" in messages.too_large_text()
