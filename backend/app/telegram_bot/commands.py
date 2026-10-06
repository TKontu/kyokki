"""Slash commands from an allowed chat: the shopping list and "used up" (CL3).

Thin over the services Home Assistant already uses (`services.ha`, `services.product_lookup`,
`services.shopping_generate`, `services.min_stock`), and after each commit it broadcasts and
runs the min-stock check exactly as the HA endpoints do, so the iPad updates live.

Logs the command and its outcome only, never the cook's text.
"""

import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.shopping_list_item import shopping_list_item as crud_shopping
from app.domain.units import canonical_factor
from app.services import ha as ha_service
from app.services import min_stock, shopping_generate
from app.services import stock as stock_service
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_shopping_list_update,
)
from app.services.product_lookup import (
    AmbiguousProduct,
    ProductNotFound,
    product_for_request,
)
from app.telegram_bot import messages

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

#: As many open lines as `/list` shows and numbers (the shopping endpoint's default page).
LIST_LIMIT = 100

# An amount, optionally with the unit glued on: "2", "0,5", "500g"
_AMOUNT = re.compile(r"^(\d+(?:[.,]\d+)?)([^\W\d_]+)?$")
_NUMBER = re.compile(r"^\d+$")


class UnknownUnit(ValueError):
    def __init__(self, unit: str) -> None:
        super().__init__(f"Unknown unit: {unit!r}")
        self.unit = unit


@dataclass(frozen=True)
class NameAmount:
    """``<name> [amount] [unit]`` from a command's arguments."""

    name: str
    amount: Decimal | None = None
    unit: str | None = None


def parse_name_amount(args: str) -> NameAmount:
    """Split ``oat milk 2 l``, ``flour 500g`` or ``eggs 6`` into name, amount and unit.

    Raises:
        UnknownUnit: An amount is followed by a word that is not a known unit.
    """
    tokens = args.split()
    if len(tokens) >= 2 and (match := _AMOUNT.match(tokens[-1])):
        name, amount, unit = tokens[:-1], match.group(1), match.group(2)
    elif (
        len(tokens) >= 3
        and (match := _AMOUNT.match(tokens[-2]))
        and match.group(2) is None
        and tokens[-1].isalpha()
    ):
        name, amount, unit = tokens[:-2], tokens[-2], tokens[-1]
    else:
        return NameAmount(name=" ".join(tokens))

    if unit is not None:
        try:
            canonical_factor(unit)
        except ValueError:
            raise UnknownUnit(unit) from None
    try:
        value = Decimal(amount.replace(",", "."))
    except InvalidOperation:  # pragma: no cover - the pattern only admits numbers
        return NameAmount(name=" ".join(tokens))
    return NameAmount(name=" ".join(name), amount=value, unit=unit)


@dataclass
class _LastList:
    """What a chat's last `/list` showed, so `/bought <n>` means the line the cook saw."""

    ids: list[UUID]
    names: list[str]
    ticked: set[UUID] = field(default_factory=set)

    def still_open(self) -> list[UUID]:
        return [item_id for item_id in self.ids if item_id not in self.ticked]


@dataclass(frozen=True)
class _Reply:
    text: str
    outcome: str


class Commands:
    """Answers one slash command. Keeps each chat's last `/list` in memory only."""

    def __init__(self, session_factory: SessionFactory):
        self.session_factory = session_factory
        self._last_lists: dict[int, _LastList] = {}

    async def handle(self, chat_id: int, text: str) -> str:
        head, _, args = text.strip().partition(" ")
        command = head.split("@", 1)[0].lower()
        args = args.strip()
        if command == "/list":
            reply = await self._list(chat_id)
        elif command == "/add":
            reply = await self._add(args)
        elif command == "/bought":
            reply = await self._bought(chat_id, args)
        elif command == "/used":
            reply = await self._used(args)
        elif command in ("/help", "/start"):
            reply = _Reply(messages.help_text(), "help")
        else:
            reply = _Reply(messages.help_text(), "unknown_command")
        logger.info(
            "Telegram command",
            extra={
                "command": command if reply.outcome != "unknown_command" else "unknown",
                "outcome": reply.outcome,
            },
        )
        return reply.text

    async def _list(self, chat_id: int) -> _Reply:
        async with self.session_factory() as db:
            rows: list[Any] = await crud_shopping.get_all(db, limit=LIST_LIMIT)
            self._last_lists[chat_id] = _LastList(
                ids=[row.id for row in rows], names=[str(row.name) for row in rows]
            )
            if not rows:
                return _Reply(messages.list_empty_text(), "empty")
            return _Reply(messages.shopping_list_text(rows), "listed")

    async def _add(self, args: str) -> _Reply:
        try:
            parsed = parse_name_amount(args)
        except UnknownUnit as exc:
            return _Reply(messages.unknown_unit_text(exc.unit), "unknown_unit")
        if not parsed.name or (parsed.amount is not None and parsed.amount <= 0):
            return _Reply(messages.add_usage_text(), "usage")

        async with self.session_factory() as db:
            product: Any
            try:
                product = await product_for_request(
                    db, name=parsed.name, product_id=None
                )
            except (ProductNotFound, AmbiguousProduct):
                # Unresolved or ambiguous: a free-text line, which a restock does not tick off
                product = None
            unit = parsed.unit or (str(product.default_unit) if product else "pcs")
            name = str(product.canonical_name) if product else parsed.name
            item_in = ha_service.shopping_add_item(
                name, parsed.amount or Decimal(1), unit
            )
            if product is not None:
                item_in = item_in.model_copy(update={"product_master_id": product.id})
            item: Any = await shopping_generate.create_item(db, item_in)
            snapshot = dict(
                shopping_list_item_id=item.id,
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                priority=item.priority,
            )

        await broadcast_shopping_list_update(
            action="created", is_purchased=False, **snapshot
        )
        return _Reply(
            messages.added_text(
                str(snapshot["name"]),
                Decimal(snapshot["quantity"]),
                str(snapshot["unit"]),
                linked=product is not None,
            ),
            "linked" if product is not None else "free_text",
        )

    async def _bought(self, chat_id: int, args: str) -> _Reply:
        if not args:
            return _Reply(messages.bought_usage_text(), "usage")
        if _NUMBER.match(args):
            return await self._bought_number(chat_id, int(args))
        return await self._bought_name(chat_id, args)

    async def _bought_number(self, chat_id: int, number: int) -> _Reply:
        last = self._last_lists.get(chat_id)
        if last is None:
            return _Reply(messages.list_changed_text(), "no_list")
        if not 1 <= number <= len(last.ids):
            return _Reply(
                messages.no_such_number_text(number, len(last.ids)), "out_of_range"
            )
        target = last.ids[number - 1]
        if target in last.ticked:
            return _Reply(messages.bought_text(last.names[number - 1]), "already")

        async with self.session_factory() as db:
            rows: list[Any] = await crud_shopping.get_all(db, limit=LIST_LIMIT)
            if [row.id for row in rows] != last.still_open():
                return _Reply(messages.list_changed_text(), "stale")
            return await self._tick(db, chat_id, target)

    async def _bought_name(self, chat_id: int, name: str) -> _Reply:
        key = name.casefold()
        async with self.session_factory() as db:
            rows: list[Any] = await crud_shopping.get_all(db, limit=LIST_LIMIT)
            matches = [row for row in rows if str(row.name).casefold() == key] or [
                row for row in rows if key in str(row.name).casefold()
            ]
            if not matches:
                return _Reply(messages.bought_not_found_text(name), "not_found")
            if len(matches) > 1:
                return _Reply(
                    messages.bought_ambiguous_text([str(row.name) for row in matches]),
                    "ambiguous",
                )
            return await self._tick(db, chat_id, matches[0].id)

    async def _tick(self, db: AsyncSession, chat_id: int, item_id: UUID) -> _Reply:
        item: Any = await shopping_generate.mark_purchased(db, item_id, purchased=True)
        if item is None:
            return _Reply(messages.list_changed_text(), "gone")
        last = self._last_lists.get(chat_id)
        if last is not None and item_id in last.ids:
            last.ticked.add(item_id)
        await broadcast_shopping_list_update(
            shopping_list_item_id=item.id,
            action="purchased",
            name=item.name,
            quantity=item.quantity,
            unit=item.unit,
            priority=item.priority,
            is_purchased=item.is_purchased,
        )
        return _Reply(messages.bought_text(str(item.name)), "ticked")

    async def _used(self, args: str) -> _Reply:
        try:
            parsed = parse_name_amount(args)
        except UnknownUnit as exc:
            return _Reply(messages.unknown_unit_text(exc.unit), "unknown_unit")
        if not parsed.name or (parsed.amount is not None and parsed.amount <= 0):
            return _Reply(messages.used_usage_text(), "usage")

        async with self.session_factory() as db:
            amount, unit = parsed.amount, parsed.unit
            if amount is None or unit is None:
                product: Any
                try:
                    product = await product_for_request(
                        db, name=parsed.name, product_id=None
                    )
                except ProductNotFound:
                    return _Reply(messages.not_found_text(parsed.name), "not_found")
                except AmbiguousProduct as exc:
                    return _ambiguous(parsed.name, exc)
                if amount is None:
                    if product.unit_type != "count":
                        return _Reply(
                            messages.used_needs_amount_text(
                                str(product.canonical_name), str(product.default_unit)
                            ),
                            "needs_amount",
                        )
                    amount, unit = Decimal(1), "pcs"
                unit = unit or str(product.default_unit)

            try:
                response, result = await ha_service.consume_by_name(
                    db, parsed.name, amount, unit
                )
            except ProductNotFound:
                return _Reply(messages.not_found_text(parsed.name), "not_found")
            except AmbiguousProduct as exc:
                return _ambiguous(parsed.name, exc)
            except stock_service.InsufficientStock as exc:
                return _Reply(
                    messages.insufficient_text(parsed.name, exc.available, exc.unit),
                    "insufficient",
                )
            except (stock_service.InvalidConsume, ValidationError) as exc:
                return _Reply(messages.invalid_consume_text(str(exc)), "invalid")

            # Committed: broadcast and check the minimum, as `POST /api/ha/consume` does
            for used in result.consumed:
                await broadcast_inventory_update(
                    inventory_item_id=used.item_id,
                    action="consumed",
                    current_quantity=Decimal(used.remaining),
                    status=used.status,
                    product_name=result.product_name,
                )
            await min_stock.after_stock_decrease(db, result.product_id)

        return _Reply(
            messages.used_text(
                response.item.name,
                response.item.quantity_before,
                response.item.quantity_after,
                result.unit,
            ),
            "consumed",
        )


def _ambiguous(name: str, exc: AmbiguousProduct) -> _Reply:
    return _Reply(
        messages.ambiguous_text(name, [candidate.name for candidate in exc.candidates]),
        "ambiguous",
    )
