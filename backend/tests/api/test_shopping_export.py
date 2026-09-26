"""AG6: GET /api/shopping/export - the open list as plain text or a Markdown checklist."""

from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shopping_list_item import ShoppingListItem

URL = "/api/shopping/export"


async def _item(
    db: AsyncSession,
    name: str,
    quantity: str,
    unit: str,
    *,
    priority: str = "normal",
    purchased: bool = False,
) -> None:
    db.add(
        ShoppingListItem(
            id=uuid4(),
            name=name,
            quantity=Decimal(quantity),
            unit=unit,
            priority=priority,
            source="manual",
            is_purchased=purchased,
        )
    )
    await db.commit()


async def _list(db: AsyncSession) -> None:
    await _item(db, "milk", "10", "dl")
    await _item(db, "Butter", "500", "g")
    await _item(db, "Mämmi", "1.5", "pcs", priority="urgent")
    await _item(db, "Apples", "6", "pcs", priority="low")
    await _item(db, "Bread", "1", "pcs", purchased=True)


class TestExport:
    async def test_text_lists_the_open_items_urgent_first_then_by_name(
        self, client: AsyncClient, test_db
    ) -> None:
        await _list(test_db)

        response = await client.get(URL, params={"format": "text"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.text == (
            "- Mämmi 1.5 pcs\n- Butter 500 g\n- milk 10 dl\n- Apples 6 pcs\n"
        )

    async def test_text_is_the_default(self, client: AsyncClient, test_db) -> None:
        await _item(test_db, "Milk", "2", "dl")

        response = await client.get(URL)

        assert response.status_code == 200
        assert response.text == "- Milk 2 dl\n"

    async def test_markdown_is_a_checklist(self, client: AsyncClient, test_db) -> None:
        await _list(test_db)

        response = await client.get(URL, params={"format": "markdown"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert response.content.decode("utf-8") == (
            "- [ ] Mämmi (1.5 pcs)\n"
            "- [ ] Butter (500 g)\n"
            "- [ ] milk (10 dl)\n"
            "- [ ] Apples (6 pcs)\n"
        )

    async def test_an_empty_list_is_empty(self, client: AsyncClient, test_db) -> None:
        response = await client.get(URL, params={"format": "markdown"})

        assert response.status_code == 200
        assert response.text == ""

    async def test_an_unknown_format_is_invalid(
        self, client: AsyncClient, test_db
    ) -> None:
        response = await client.get(URL, params={"format": "pdf"})

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid"

    async def test_export_is_not_taken_for_an_item_id(
        self, client: AsyncClient, test_db
    ) -> None:
        """Declared before /{item_id}: otherwise "export" is parsed as a UUID and 422s."""
        response = await client.get(URL)

        assert response.status_code == 200
