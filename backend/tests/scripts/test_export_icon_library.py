"""Export good generated icons from a deployment into the repo's icon library.

GET only, against a mocked API (`httpx.MockTransport`) - never the real deployment, which
is the planner's job once this lane is done (see the script's own module docstring).
"""

from __future__ import annotations

import hashlib
import io
import json

import httpx
import pytest
from PIL import Image
from scripts import export_icon_library as export_script


def _png(
    colour: tuple[int, int, int, int] = (228, 69, 58, 255), size: int = 8
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), colour).save(buffer, format="PNG")
    return buffer.getvalue()


QUARK_PNG = _png((255, 255, 255, 255))
LEEK_PNG = _png((0, 200, 0, 255))


def _product(
    id_: str,
    name: str,
    *,
    icon_status: str | None = "ready",
    emoji_match: str | None = None,
    icon_seed: int | None = 12345,
) -> dict:
    return {
        "id": id_,
        "canonical_name": name,
        "icon_status": icon_status,
        "icon_seed": icon_seed,
        "emoji_match": emoji_match,
    }


def _server(products: list[dict], icons: dict[str, bytes]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/products":
            return httpx.Response(200, json=products)
        if request.url.path.endswith("/icon.png"):
            product_id = request.url.path.split("/")[-2]
            if product_id in icons:
                return httpx.Response(200, content=icons[product_id])
            return httpx.Response(404)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _client(products: list[dict], icons: dict[str, bytes]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_server(products, icons), base_url="http://fake-deployment:17300"
    )


class TestSelection:
    async def test_all_ready_picks_every_eligible_product(self, tmp_path) -> None:
        products = [
            _product("1", "Quark"),
            _product("2", "Leek"),
        ]
        icons = {"1": QUARK_PNG, "2": LEEK_PNG}

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, icons),
        )

        assert result.eligible == 2
        assert result.exported == 2

    async def test_a_non_ready_status_is_excluded(self, tmp_path) -> None:
        products = [_product("1", "Quark", icon_status="pending")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {}),
        )

        assert result.eligible == 0

    async def test_an_exact_emoji_win_is_excluded(self, tmp_path) -> None:
        products = [_product("1", "Quark", emoji_match="exact")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {}),
        )

        assert result.eligible == 0

    async def test_a_cook_emoji_win_is_excluded(self, tmp_path) -> None:
        products = [_product("1", "Quark", emoji_match="cook")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {}),
        )

        assert result.eligible == 0

    async def test_a_null_icon_seed_is_excluded_already_a_library_icon(
        self, tmp_path
    ) -> None:
        """A NULL `icon_seed` on the deployment means its own icon already came from a
        library (or was never actually rendered) - not worth re-exporting."""
        products = [_product("1", "Quark", icon_seed=None)]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {}),
        )

        assert result.eligible == 0

    async def test_names_restricts_to_the_given_products(self, tmp_path) -> None:
        products = [_product("1", "Quark"), _product("2", "Leek")]
        icons = {"1": QUARK_PNG, "2": LEEK_PNG}

        result = await export_script.export(
            "http://fake-deployment:17300",
            names=["Quark"],
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, icons),
        )

        assert result.eligible == 1
        assert result.exported == 1
        assert (tmp_path / "lib" / "quark.png").exists()
        assert not (tmp_path / "lib" / "leek.png").exists()

    async def test_without_names_or_all_ready_nothing_is_eligible(
        self, tmp_path
    ) -> None:
        products = [_product("1", "Quark")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        assert result.eligible == 0

    async def test_an_entry_already_in_the_library_is_skipped_without_replace(
        self, tmp_path
    ) -> None:
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "index.json").write_text(
            json.dumps({"quark": {"file": "quark.png", "sha256": "whatever"}}),
            encoding="utf-8",
        )
        products = [_product("1", "Quark")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=lib_dir,
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        assert result.eligible == 1
        assert result.exported == 0
        assert result.skipped_existing == 1

    async def test_replace_overwrites_an_existing_entry(self, tmp_path) -> None:
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "quark.png").write_bytes(b"old bytes")
        (lib_dir / "index.json").write_text(
            json.dumps(
                {
                    "quark": {
                        "file": "quark.png",
                        "sha256": hashlib.sha256(b"old bytes").hexdigest(),
                    }
                }
            ),
            encoding="utf-8",
        )
        products = [_product("1", "Quark")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            replace=True,
            library_dir=lib_dir,
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        assert result.replaced == 1
        assert (lib_dir / "quark.png").read_bytes() == QUARK_PNG


class TestDryRun:
    async def test_dry_run_lists_exactly_the_eligible_products_and_writes_nothing(
        self, tmp_path
    ) -> None:
        products = [
            _product("1", "Quark"),
            _product("2", "Leek", icon_status="failed"),
            _product("3", "Ketchup", emoji_match="exact"),
        ]
        lib_dir = tmp_path / "lib"

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            dry_run=True,
            library_dir=lib_dir,
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        assert result.eligible == 1
        assert any("would export  Quark" in line for line in result.lines)
        assert not lib_dir.exists()

    async def test_dry_run_does_not_list_an_entry_already_in_the_library(
        self, tmp_path
    ) -> None:
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "index.json").write_text(
            json.dumps({"quark": {"file": "quark.png", "sha256": "whatever"}}),
            encoding="utf-8",
        )
        products = [_product("1", "Quark")]

        result = await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            dry_run=True,
            library_dir=lib_dir,
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        assert not any("would export" in line for line in result.lines)
        assert result.skipped_existing == 1


class TestWriting:
    async def test_it_writes_the_png_and_the_index_entry(self, tmp_path) -> None:
        products = [_product("1", "Quark", icon_seed=987)]
        lib_dir = tmp_path / "lib"

        await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=lib_dir,
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        png_path = lib_dir / "quark.png"
        assert png_path.read_bytes() == QUARK_PNG
        index = json.loads((lib_dir / "index.json").read_text(encoding="utf-8"))
        entry = index["quark"]
        assert entry["file"] == "quark.png"
        assert entry["sha256"] == hashlib.sha256(QUARK_PNG).hexdigest()
        assert entry["seed"] == 987
        assert entry["source"] == "generated:fake-deployment:17300"
        assert entry["exported_at"]

    async def test_the_subject_falls_back_to_the_cached_icon_subject(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            export_script, "subject_for", lambda name: "a tub of soft white cheese"
        )
        products = [_product("1", "Quark")]
        lib_dir = tmp_path / "lib"

        await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=lib_dir,
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=_client(products, {"1": QUARK_PNG}),
        )

        index = json.loads((lib_dir / "index.json").read_text(encoding="utf-8"))
        assert index["quark"]["subject"] == "a tub of soft white cheese"

    async def test_the_contact_sheet_is_written_for_a_real_export(
        self, tmp_path
    ) -> None:
        products = [_product("1", "Quark"), _product("2", "Leek")]
        icons = {"1": QUARK_PNG, "2": LEEK_PNG}
        sheet_path = tmp_path / "sheet.png"

        await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=sheet_path,
            http_client=_client(products, icons),
        )

        assert sheet_path.exists()
        with Image.open(sheet_path) as sheet:
            assert sheet.size[0] > 0 and sheet.size[1] > 0

    async def test_no_contact_sheet_when_nothing_was_exported(self, tmp_path) -> None:
        products: list[dict] = []
        sheet_path = tmp_path / "sheet.png"

        await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=sheet_path,
            http_client=_client(products, {}),
        )

        assert not sheet_path.exists()

    async def test_dry_run_never_calls_the_icon_endpoint(self, tmp_path) -> None:
        products = [_product("1", "Quark")]
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/api/products":
                return httpx.Response(200, json=products)
            return httpx.Response(200, content=QUARK_PNG)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://fake-deployment:17300",
        )

        await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            dry_run=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=client,
        )

        assert not any(path.endswith("icon.png") for path in calls)


class TestNeverMutatesTheDeployment:
    async def test_only_get_requests_are_ever_made(self, tmp_path) -> None:
        products = [_product("1", "Quark")]
        methods: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            methods.append(request.method)
            if request.url.path == "/api/products":
                return httpx.Response(200, json=products)
            return httpx.Response(200, content=QUARK_PNG)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://fake-deployment:17300",
        )

        await export_script.export(
            "http://fake-deployment:17300",
            all_ready=True,
            library_dir=tmp_path / "lib",
            contact_sheet_path=tmp_path / "sheet.png",
            http_client=client,
        )

        assert methods
        assert all(method == "GET" for method in methods)
