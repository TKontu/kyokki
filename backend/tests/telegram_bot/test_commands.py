"""Slash commands from an allowed chat: the shopping list and "used up" (CL3)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.receipt import Receipt
from app.models.shopping_list_item import ShoppingListItem
from app.telegram_bot import messages
from app.telegram_bot.handlers import BotHandler

from .conftest import FakeTelegram

ALLOWED = 1001
STRANGER = 2002
UNIT_TYPES = {"dl": "volume", "g": "weight", "pcs": "count"}


class FakeNotifier:
    def __init__(self):
        self.watched: list[tuple] = []

    async def watch(self, receipt_id, chat_id: int, message_id: int) -> None:
        self.watched.append((receipt_id, chat_id, message_id))


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def handler(telegram, session_factory, notifier) -> BotHandler:
    return BotHandler(
        client=telegram,
        session_factory=session_factory,
        notifier=notifier,
        allowed_chat_ids=[ALLOWED],
    )


@pytest.fixture
def broadcast():
    with (
        patch(
            "app.telegram_bot.commands.broadcast_inventory_update",
            new_callable=AsyncMock,
        ) as inventory,
        patch(
            "app.telegram_bot.commands.broadcast_shopping_list_update",
            new_callable=AsyncMock,
        ) as shopping,
    ):
        yield inventory, shopping


@pytest.fixture
def after_decrease():
    with patch(
        "app.services.min_stock.after_stock_decrease", new_callable=AsyncMock
    ) as hook:
        yield hook


@pytest.fixture
async def db(db_session: AsyncSession, sample_category) -> AsyncSession:
    return db_session


def _update(chat_id: int, **message) -> dict:
    return {
        "update_id": 1,
        "message": {"message_id": 7, "chat": {"id": chat_id}, **message},
    }


async def _say(handler: BotHandler, text: str, chat_id: int = ALLOWED) -> None:
    await handler.handle_update(_update(chat_id, text=text))


def _replies(telegram: FakeTelegram) -> list[str]:
    return [text for _, text in telegram.sent]


async def _product(db: AsyncSession, name: str, *, unit: str = "dl") -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type=UNIT_TYPES[unit],
        default_unit=unit,
    )
    db.add(product)
    db.add(
        ProductName(
            product_master_id=product.id, name=name.casefold(), source="canonical"
        )
    )
    await db.commit()
    return product


async def _item(
    db: AsyncSession, product: ProductMaster, quantity: str, *, unit: str = "dl"
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(quantity),
        current_quantity=Decimal(quantity),
        unit=unit,
        status="sealed",
        expiry_date=date.today() + timedelta(days=7),
        location="main_fridge",
    )
    db.add(item)
    await db.commit()
    return item


async def _row(
    db: AsyncSession,
    name: str,
    *,
    quantity: str = "1",
    unit: str = "pcs",
    priority: str = "normal",
    minutes_ago: int = 0,
) -> ShoppingListItem:
    row = ShoppingListItem(
        id=uuid4(),
        name=name,
        quantity=Decimal(quantity),
        unit=unit,
        priority=priority,
        source="manual",
        is_purchased=False,
        added_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(row)
    await db.commit()
    return row


async def _rows(db: AsyncSession) -> list[ShoppingListItem]:
    return list((await db.execute(select(ShoppingListItem))).scalars().all())


async def _count(db: AsyncSession, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar())


class TestAccessAndHelp:
    async def test_stranger_commands_are_ignored(
        self, handler, telegram, db, broadcast
    ):
        await _row(db, "Milk")

        for text in ("/list", "/add bread", "/bought 1", "/used milk 1 dl"):
            await _say(handler, text, chat_id=STRANGER)

        assert telegram.sent == []
        assert await _count(db, ShoppingListItem) == 1
        assert not (await _rows(db))[0].is_purchased
        broadcast[0].assert_not_awaited()
        broadcast[1].assert_not_awaited()

    async def test_help_and_start_list_the_commands(self, handler, telegram):
        await _say(handler, "/help")
        await _say(handler, "/start")

        assert _replies(telegram) == [messages.help_text(), messages.help_text()]
        for command in ("/list", "/add", "/bought", "/used"):
            assert command in messages.help_text()

    async def test_plain_text_still_gets_the_help(self, handler, telegram, db):
        await _say(handler, "list")
        await _say(handler, "milk 2 l")

        assert _replies(telegram) == [messages.help_text(), messages.help_text()]
        assert await _count(db, ShoppingListItem) == 0

    async def test_unknown_command_gets_the_help(self, handler, telegram):
        await _say(handler, "/frobnicate")

        assert _replies(telegram) == [messages.help_text()]

    async def test_photo_still_goes_to_receipt_intake(
        self, session_factory, db, notifier
    ):
        telegram = FakeTelegram({"big": (b"jpeg bytes", 900)})
        handler = BotHandler(
            client=telegram,
            session_factory=session_factory,
            notifier=notifier,
            allowed_chat_ids=[ALLOWED],
        )
        photo = [{"file_id": "big", "file_unique_id": "b", "file_size": 900}]

        await handler.handle_update(_update(ALLOWED, photo=photo, caption="/list"))

        assert telegram.downloads == ["path/big"]
        assert await _count(db, Receipt) == 1
        assert len(notifier.watched) == 1


class TestList:
    async def test_empty(self, handler, telegram, db):
        await _say(handler, "/list")

        assert _replies(telegram) == [messages.list_empty_text()]
        assert messages.list_empty_text() == "The shopping list is empty."

    async def test_open_rows_numbered_in_the_shopping_screen_order(
        self, handler, telegram, db
    ):
        await _row(db, "Bread", minutes_ago=10)
        await _row(db, "Milk", quantity="2", unit="l", priority="urgent")
        await _row(db, "Candles", priority="low", minutes_ago=20)
        bought = await _row(db, "Old", minutes_ago=30)
        bought.is_purchased = True
        await db.commit()

        await _say(handler, "/list")

        (reply,) = _replies(telegram)
        assert reply.splitlines() == [
            "1. Milk — 2 l (urgent)",
            "2. Bread — 1 pcs",
            "3. Candles — 1 pcs (low)",
        ]

    async def test_bot_name_suffix_is_accepted(self, handler, telegram, db):
        await _row(db, "Bread")

        await _say(handler, "/list@KyokkiBot")

        assert _replies(telegram) == ["1. Bread — 1 pcs"]


class TestAdd:
    async def test_free_text_defaults_to_one_pcs_and_broadcasts(
        self, handler, telegram, db, broadcast
    ):
        _, shopping = broadcast

        await _say(handler, "/add Rye bread")

        (row,) = await _rows(db)
        assert row.name == "Rye bread"
        assert row.product_master_id is None
        assert (row.quantity, row.unit) == (Decimal("1"), "pcs")
        assert _replies(telegram) == [
            messages.added_text("Rye bread", Decimal("1"), "pcs", linked=False)
        ]
        shopping.assert_awaited_once()
        assert shopping.await_args.kwargs["action"] == "created"
        assert shopping.await_args.kwargs["shopping_list_item_id"] == row.id

    async def test_amount_and_unit(self, handler, telegram, db, broadcast):
        await _say(handler, "/add oat drink 2 l")

        (row,) = await _rows(db)
        assert row.name == "oat drink"
        # Convert-on-write: litres are stored as decilitres
        assert (row.quantity, row.unit) == (Decimal("20"), "dl")

    async def test_amount_glued_to_the_unit(self, handler, telegram, db, broadcast):
        await _say(handler, "/add flour 500g")

        (row,) = await _rows(db)
        assert (row.name, row.quantity, row.unit) == ("flour", Decimal("500"), "g")

    async def test_uniquely_resolved_product_is_linked_with_its_default_unit(
        self, handler, telegram, db, broadcast
    ):
        milk = await _product(db, "Milk", unit="dl")

        await _say(handler, "/add milk")

        (row,) = await _rows(db)
        assert row.product_master_id == milk.id
        assert row.name == "Milk"
        assert (row.quantity, row.unit) == (Decimal("1"), "dl")
        assert _replies(telegram) == [
            messages.added_text("Milk", Decimal("1"), "dl", linked=True)
        ]

    async def test_ambiguous_name_stays_free_text(
        self, handler, telegram, db, broadcast
    ):
        await _product(db, "Oat milk")
        await _product(db, "Soy milk")

        await _say(handler, "/add milk")

        (row,) = await _rows(db)
        assert row.product_master_id is None
        assert (row.name, row.unit) == ("milk", "pcs")
        assert "not linked" in _replies(telegram)[0]

    async def test_without_a_name_explains_the_usage(
        self, handler, telegram, db, broadcast
    ):
        await _say(handler, "/add")

        assert _replies(telegram) == [messages.add_usage_text()]
        assert await _count(db, ShoppingListItem) == 0
        broadcast[1].assert_not_awaited()

    async def test_unknown_unit_is_refused(self, handler, telegram, db, broadcast):
        await _say(handler, "/add milk 2 bottles")

        assert _replies(telegram) == [messages.unknown_unit_text("bottles")]
        assert await _count(db, ShoppingListItem) == 0


class TestBought:
    async def test_number_from_the_last_list(self, handler, telegram, db, broadcast):
        _, shopping = broadcast
        bread = await _row(db, "Bread", minutes_ago=5)
        milk = await _row(db, "Milk")

        await _say(handler, "/list")
        await _say(handler, "/bought 2")

        await db.refresh(milk)
        await db.refresh(bread)
        assert milk.is_purchased
        assert not bread.is_purchased
        assert _replies(telegram)[-1] == messages.bought_text("Milk")
        shopping.assert_awaited_once()
        assert shopping.await_args.kwargs["action"] == "purchased"
        assert shopping.await_args.kwargs["is_purchased"] is True

    async def test_numbers_keep_meaning_what_the_cook_saw_after_a_tick(
        self, handler, telegram, db, broadcast
    ):
        bread = await _row(db, "Bread", minutes_ago=5)
        milk = await _row(db, "Milk")

        await _say(handler, "/list")
        await _say(handler, "/bought 1")
        await _say(handler, "/bought 2")

        await db.refresh(milk)
        await db.refresh(bread)
        assert bread.is_purchased and milk.is_purchased
        assert _replies(telegram)[-2:] == [
            messages.bought_text("Bread"),
            messages.bought_text("Milk"),
        ]

    async def test_stale_number_is_refused(self, handler, telegram, db, broadcast):
        bread = await _row(db, "Bread", minutes_ago=5)
        await _say(handler, "/list")
        # Someone adds an urgent line on the iPad: the numbering shifts
        await _row(db, "Eggs", priority="urgent")

        await _say(handler, "/bought 1")

        await db.refresh(bread)
        assert not bread.is_purchased
        assert _replies(telegram)[-1] == messages.list_changed_text()
        broadcast[1].assert_not_awaited()

    async def test_number_without_a_list_is_refused(
        self, handler, telegram, db, broadcast
    ):
        bread = await _row(db, "Bread")

        await _say(handler, "/bought 1")

        await db.refresh(bread)
        assert not bread.is_purchased
        assert _replies(telegram) == [messages.list_changed_text()]

    async def test_number_out_of_range(self, handler, telegram, db, broadcast):
        await _row(db, "Bread")
        await _say(handler, "/list")

        await _say(handler, "/bought 5")

        assert _replies(telegram)[-1] == messages.no_such_number_text(5, 1)
        broadcast[1].assert_not_awaited()

    async def test_name_ticks_the_single_matching_row(
        self, handler, telegram, db, broadcast
    ):
        bread = await _row(db, "Rye bread")
        await _row(db, "Milk")

        await _say(handler, "/bought rye BREAD")

        await db.refresh(bread)
        assert bread.is_purchased
        assert _replies(telegram) == [messages.bought_text("Rye bread")]

    async def test_name_matching_several_rows_is_refused(
        self, handler, telegram, db, broadcast
    ):
        await _row(db, "Rye bread")
        await _row(db, "White bread")

        await _say(handler, "/bought bread")

        assert _replies(telegram) == [
            messages.bought_ambiguous_text(["Rye bread", "White bread"])
        ]
        assert not any(row.is_purchased for row in await _rows(db))

    async def test_unknown_name(self, handler, telegram, db, broadcast):
        await _row(db, "Milk")

        await _say(handler, "/bought caviar")

        assert _replies(telegram) == [messages.bought_not_found_text("caviar")]
        broadcast[1].assert_not_awaited()

    async def test_without_an_argument_explains_the_usage(
        self, handler, telegram, db, broadcast
    ):
        await _say(handler, "/bought")

        assert _replies(telegram) == [messages.bought_usage_text()]


class TestUsed:
    async def test_consumes_broadcasts_and_runs_the_min_stock_check(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        inventory, _ = broadcast
        milk = await _product(db, "Milk")
        item = await _item(db, milk, "10")

        await _say(handler, "/used milk 3 dl")

        await db.refresh(item)
        assert item.current_quantity == Decimal("7")
        assert _replies(telegram) == [
            messages.used_text("Milk", Decimal("10"), Decimal("7"), "dl")
        ]
        inventory.assert_awaited_once()
        assert inventory.await_args.kwargs["action"] == "consumed"
        assert inventory.await_args.kwargs["inventory_item_id"] == item.id
        after_decrease.assert_awaited_once()
        assert after_decrease.await_args.args[1] == milk.id

    async def test_converts_the_unit(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        milk = await _product(db, "Milk")
        item = await _item(db, milk, "10")

        await _say(handler, "/used milk 0.5 l")

        await db.refresh(item)
        assert item.current_quantity == Decimal("5")

    async def test_count_product_without_an_amount_uses_one_pcs(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        eggs = await _product(db, "Eggs", unit="pcs")
        item = await _item(db, eggs, "6", unit="pcs")

        await _say(handler, "/used eggs")

        await db.refresh(item)
        assert item.current_quantity == Decimal("5")
        assert _replies(telegram) == [
            messages.used_text("Eggs", Decimal("6"), Decimal("5"), "pcs")
        ]

    async def test_measured_product_without_an_amount_asks_for_one(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        milk = await _product(db, "Milk")
        item = await _item(db, milk, "10")

        await _say(handler, "/used milk")

        await db.refresh(item)
        assert item.current_quantity == Decimal("10")
        assert _replies(telegram) == [messages.used_needs_amount_text("Milk", "dl")]
        broadcast[0].assert_not_awaited()
        after_decrease.assert_not_awaited()

    async def test_amount_without_a_unit_uses_the_product_unit(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        milk = await _product(db, "Milk")
        item = await _item(db, milk, "10")

        await _say(handler, "/used milk 2")

        await db.refresh(item)
        assert item.current_quantity == Decimal("8")

    async def test_unknown_product(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        await _say(handler, "/used caviar 1 g")

        assert _replies(telegram) == [messages.not_found_text("caviar")]
        broadcast[0].assert_not_awaited()
        after_decrease.assert_not_awaited()

    async def test_ambiguous_product_lists_at_most_five_candidates(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        for name in ("Oat milk", "Soy milk", "Rice milk", "Milk powder"):
            product = await _product(db, name)
            await _item(db, product, "10")
        for name in ("Almond milk", "Coconut milk"):
            await _product(db, name)

        await _say(handler, "/used milk 1 dl")

        (reply,) = _replies(telegram)
        assert reply.startswith("Which one")
        assert len(reply.splitlines()) - 1 <= 5
        items = (await db.execute(select(InventoryItem))).scalars().all()
        assert all(item.current_quantity == Decimal("10") for item in items)
        broadcast[0].assert_not_awaited()
        after_decrease.assert_not_awaited()

    async def test_ambiguous_without_an_amount_also_lists_candidates(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        await _product(db, "Oat milk")

        await _say(handler, "/used milk")

        (reply,) = _replies(telegram)
        assert reply.startswith("Which one")
        assert "Oat milk" in reply

    async def test_insufficient_stock_changes_nothing(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        milk = await _product(db, "Milk")
        item = await _item(db, milk, "2")

        await _say(handler, "/used milk 5 dl")

        await db.refresh(item)
        assert item.current_quantity == Decimal("2")
        assert _replies(telegram) == [
            messages.insufficient_text("milk", Decimal("2"), "dl")
        ]
        broadcast[0].assert_not_awaited()
        after_decrease.assert_not_awaited()

    async def test_unit_that_fits_no_item_is_refused(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        milk = await _product(db, "Milk")
        item = await _item(db, milk, "10")

        await _say(handler, "/used milk 5 g")

        await db.refresh(item)
        assert item.current_quantity == Decimal("10")
        assert _replies(telegram)[0].startswith("Nothing changed")
        after_decrease.assert_not_awaited()

    async def test_without_a_name_explains_the_usage(
        self, handler, telegram, db, broadcast, after_decrease
    ):
        await _say(handler, "/used")

        assert _replies(telegram) == [messages.used_usage_text()]
