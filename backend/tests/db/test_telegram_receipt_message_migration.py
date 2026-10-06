"""CL5: the `telegram_receipt_message` table, the bot's durable list of results owed."""

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"


def _load_migration():
    (path,) = VERSIONS.glob("*_telegram_receipt_message.py")
    spec = importlib.util.spec_from_file_location(
        "telegram_receipt_message_migration", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_icon_curation(self) -> None:
        assert _load_migration().down_revision == "c9a51b6756c1"

    def test_it_is_the_only_head(self) -> None:
        (head,) = _script().get_heads()
        assert head == _load_migration().revision

    def test_history_stays_one_line_through_it(self) -> None:
        script = _script()
        (head,) = script.get_heads()
        ancestors = {rev.revision for rev in script.walk_revisions("base", head)}
        assert _load_migration().revision in ancestors
