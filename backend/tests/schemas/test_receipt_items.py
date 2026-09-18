"""Turning a stored receipt blob into typed review items.

`items_from_structured` is the boundary every receipt in the database passes through,
including ones written before the current shape, so it has to read both vocabularies
without failing the response.
"""

import pytest

from app.schemas.receipt import items_from_structured

LINE_A = "11111111-1111-1111-1111-111111111111"
LINE_B = "22222222-2222-2222-2222-222222222222"


class TestLineIdentity:
    """H12: a line can be addressed by identity rather than by position.

    `index` is the position in the *stored* list - `enumerate` runs over every line and
    unreadable ones are skipped rather than renumbered - so it agrees with confirm's
    lookup and is not broken. What it cannot do is survive a re-read, which produces a
    fresh list of lines; `line_id` is what carries a line's identity across one.
    """

    def test_a_line_id_survives_into_the_typed_item(self) -> None:
        items = items_from_structured(
            {
                "lines": [
                    {"name": "MAITO", "quantity": 1, "line_id": LINE_A},
                ]
            }
        )

        assert str(items[0].line_id) == LINE_A

    def test_an_unreadable_line_does_not_renumber_the_ones_after_it(self) -> None:
        """Worth pinning: `index` is the stored position, so it still points at the
        right line after an unreadable one, which is what confirm relies on."""
        items = items_from_structured(
            {
                "lines": [
                    {"name": "", "quantity": 1, "line_id": LINE_A},
                    {"name": "MAITO", "quantity": 1, "line_id": LINE_B},
                ]
            }
        )

        assert [item.index for item in items] == [1]
        assert str(items[0].line_id) == LINE_B

    def test_a_receipt_read_before_h12_still_renders(self) -> None:
        """Receipts already in the database have neither key."""
        items = items_from_structured(
            {"lines": [{"name": "MAITO", "quantity": 1, "match_source": "alias"}]}
        )

        assert items[0].line_id is None
        assert items[0].match_source == "alias"
        assert items[0].verified is False


class TestMatchSourceVocabulary:
    @pytest.mark.parametrize(
        ("stored", "expected"),
        [
            ("alias", "alias"),
            ("exact", "name"),
            ("fuzzy", "selected"),
            ("fuzzy_alias", "selected"),
            ("name", "name"),
            ("selected", "selected"),
            ("none", "none"),
            (None, None),
            ("something else", None),
        ],
    )
    def test_both_vocabularies_are_understood(self, stored, expected) -> None:
        """`fuzzy` was a similarity guess, which is what `selected` now means to the
        review row: proposed, not keyed."""
        items = items_from_structured(
            {"lines": [{"name": "MAITO", "quantity": 1, "match_source": stored}]}
        )

        assert items[0].match_source == expected

    def test_the_resolution_block_wins_over_the_legacy_field(self) -> None:
        items = items_from_structured(
            {
                "lines": [
                    {
                        "name": "MAITO",
                        "quantity": 1,
                        "match_source": "fuzzy",
                        "resolution": {"source": "alias", "verified": True},
                    }
                ]
            }
        )

        assert (items[0].match_source, items[0].verified) == ("alias", True)

    def test_verified_is_false_unless_the_resolution_says_otherwise(self) -> None:
        items = items_from_structured(
            {
                "lines": [
                    {
                        "name": "MAITO",
                        "quantity": 1,
                        "resolution": {"source": "selected", "verified": False},
                    }
                ]
            }
        )

        assert items[0].verified is False
