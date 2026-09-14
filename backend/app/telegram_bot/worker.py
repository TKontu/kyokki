"""Read queued receipts one at a time and replace the acknowledgement with the result.

The extraction model serves one request at a time and a receipt takes about a minute, so a
single sequential worker is enough. After MVP-R3 this hands off to the background job instead.
"""

import asyncio

from app.core.logging import get_logger
from app.crud import receipt as crud_receipt
from app.schemas.receipt import ReceiptResponse
from app.services.receipt_processing import ReceiptProcessingService
from app.telegram_bot import messages
from app.telegram_bot.client import TelegramError
from app.telegram_bot.handlers import BotApi, Job, SessionFactory

logger = get_logger(__name__)


class ReceiptWorker:
    def __init__(self, client: BotApi, session_factory: SessionFactory):
        self.client = client
        self.session_factory = session_factory

    async def run(self, queue: "asyncio.Queue[Job]") -> None:
        while True:
            job = await queue.get()
            try:
                await self.run_job(job)
            except Exception:
                logger.exception(
                    "Telegram job crashed", extra={"receipt_id": str(job.receipt_id)}
                )
            finally:
                queue.task_done()

    async def run_job(self, job: Job) -> None:
        text = await self._process(job)
        try:
            await self.client.edit_message_text(job.chat_id, job.message_id, text)
        except TelegramError as exc:
            # The acknowledgement may be gone; send the result as a new message instead
            logger.warning(
                "Could not edit the acknowledgement", extra={"error": str(exc)}
            )
            await self.client.send_message(job.chat_id, text)

    async def _process(self, job: Job) -> str:
        receipt_id = str(job.receipt_id)
        try:
            async with self.session_factory() as db:
                receipt = await crud_receipt.get_receipt(db, job.receipt_id)
                if receipt is None:
                    return messages.failure_text("the receipt was deleted")
                result = await ReceiptProcessingService(db).process_receipt(receipt)
                if not result.success:
                    logger.warning(
                        "Telegram receipt could not be read",
                        extra={"receipt_id": receipt_id, "error": result.error},
                    )
                    return messages.failure_text(result.error)
                await db.refresh(receipt)
                return messages.result_text(ReceiptResponse.model_validate(receipt))
        except Exception:
            logger.exception(
                "Telegram receipt processing crashed", extra={"receipt_id": receipt_id}
            )
            return messages.failure_text("unexpected error")
