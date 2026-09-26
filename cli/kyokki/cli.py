"""``kyokki``: the argparse front end. Parse, call the API, print, return an exit code."""

import argparse
import math
import os
import sys
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from kyokki import api, commands, idempotency, output
from kyokki.api import USAGE, Api, CliError

LOCATIONS = ["main_fridge", "freezer", "pantry"]
UNITS_HELP = (
    "dl, tsp, tbsp, g, pcs (l, ml, kg and the like are converted by the server)"
)
MAX_KEY_LENGTH = 255

EXIT_CODES = """\
exit codes:
  0 ok
  1 error: unreachable, server error (5xx) or an unexpected answer
  2 usage: bad arguments, or the API rejected the request (400 invalid, 422)
  3 not found
  4 ambiguous name: the candidates are printed on stdout
  5 insufficient stock
  6 conflict: the name belongs to another product, or a reused Idempotency-Key
  7 auth: missing or unknown token (401), or a read token on a write (403)"""

ENVIRONMENT = """\
environment:
  KYOKKI_URL    base URL of the Kyokki server (overridden by --url)
  KYOKKI_TOKEN  API token (overridden by --token); sent as a Bearer header only"""


def epilog(*examples: str, extra: str = "") -> str:
    lines = ["examples:", *(f"  {example}" for example in examples)]
    parts = ["\n".join(lines)]
    if extra:
        parts.append(extra)
    parts.append(EXIT_CODES)
    return "\n\n".join(parts)


# --- argument types -----------------------------------------------------------


def positive_number(text: str) -> int | float:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not value.is_finite() or value <= 0 or not math.isfinite(float(value)):
        raise argparse.ArgumentTypeError(f"must be a number above 0: {text!r}")
    return int(value) if value == value.to_integral_value() else float(value)


def non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more: {text!r}")
    return value


def iso_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from None


def product_id(text: str) -> str:
    if not commands.looks_like_uuid(text):
        raise argparse.ArgumentTypeError(
            f"not a product id (a UUID): {text!r}; find it with kyokki product resolve"
        )
    return text


def idempotency_key(text: str) -> str:
    if not text or len(text) > MAX_KEY_LENGTH:
        raise argparse.ArgumentTypeError(
            f"an idempotency key is 1 to {MAX_KEY_LENGTH} characters"
        )
    return text


# --- the parser ---------------------------------------------------------------

Formatter = argparse.RawDescriptionHelpFormatter


def add_connection_options(parser: argparse.ArgumentParser, *, top: bool) -> None:
    """--url, --token, --json, --verbose: at the top, and again after any command.

    Below the top level the defaults are SUPPRESS, so a leaf never overwrites a value
    given before the command.
    """
    default = None if top else argparse.SUPPRESS
    flag_default = False if top else argparse.SUPPRESS
    group = parser.add_argument_group("connection and output")
    group.add_argument(
        "--url",
        default=default,
        help="Kyokki base URL, e.g. http://kyokki.lan:8000 (default: $KYOKKI_URL)",
    )
    group.add_argument(
        "--token",
        default=default,
        help="API token, sent as a Bearer header and never printed "
        "(default: $KYOKKI_TOKEN)",
    )
    group.add_argument(
        "--json",
        action="store_true",
        default=flag_default,
        help="print the API's JSON (the default when stdout is not a terminal)",
    )
    group.add_argument(
        "--verbose",
        action="store_true",
        default=flag_default,
        help="log each request and its status to stderr",
    )


def add_idempotency_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--idempotency-key",
        type=idempotency_key,
        metavar="KEY",
        help="retry key (at most 255 characters); default: SHA-256 of this command "
        "line and the UTC minute, so a retry within the minute is safe",
    )


def leaf(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
    name: str,
    *,
    summary: str,
    description: str,
    examples: list[str],
    handler: Callable[[commands.Context], commands.Outcome],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        name,
        help=summary,
        description=description,
        epilog=epilog(*examples),
        formatter_class=Formatter,
        allow_abbrev=False,
    )
    parser.set_defaults(handler=handler)
    return parser


def group(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
    name: str,
    *,
    summary: str,
    description: str,
    examples: list[str],
) -> "argparse._SubParsersAction[argparse.ArgumentParser]":
    parser = subparsers.add_parser(
        name,
        help=summary,
        description=description,
        epilog=epilog(*examples),
        formatter_class=Formatter,
        allow_abbrev=False,
    )
    children = parser.add_subparsers(
        title="commands", dest=f"{name}_command", metavar="COMMAND", required=True
    )
    return children


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyokki",
        description="Read and change the Kyokki kitchen inventory over its HTTP API.\n"
        "Built for agents: stable exit codes, and JSON whenever stdout is not a "
        "terminal.",
        epilog=epilog(
            "kyokki doctor",
            "kyokki stock list --expiring 3",
            "kyokki stock consume milk 2 dl --dry-run",
            extra=ENVIRONMENT,
        ),
        formatter_class=Formatter,
        allow_abbrev=False,
    )
    add_connection_options(parser, top=True)
    top = parser.add_subparsers(
        title="commands", dest="command", metavar="COMMAND", required=True
    )

    doctor = leaf(
        top,
        "doctor",
        summary="check the connection and the token",
        description="Check that the server answers (/api/health/live), then which token\n"
        "you are, its scopes, and whether the server has auth on.",
        examples=[
            "kyokki doctor",
            "kyokki doctor --url http://kyokki.lan:8000 --json",
        ],
        handler=commands.doctor,
    )
    add_connection_options(doctor, top=False)

    # stock
    stock = group(
        top,
        "stock",
        summary="list, add and consume stock",
        description="What is in the kitchen, per product, and changing it.",
        examples=[
            "kyokki stock list --location freezer",
            "kyokki stock add milk 1 l --category dairy",
            "kyokki stock consume milk 2 dl",
        ],
    )

    listing = leaf(
        stock,
        "list",
        summary="stock per product, soonest to expire first",
        description="Stock per product (and unit), summed over its items, soonest to\n"
        "expire first. A row marked ! expires within 3 days or already has.",
        examples=[
            "kyokki stock list",
            "kyokki stock list --q milk --location main_fridge",
            "kyokki stock list --expiring 3 --json",
        ],
        handler=commands.stock_list,
    )
    listing.add_argument("--q", metavar="NAME", help="part of a product name, any case")
    listing.add_argument("--location", choices=LOCATIONS, help="only this location")
    listing.add_argument(
        "--expiring",
        type=non_negative_int,
        metavar="DAYS",
        help="only products expiring within DAYS days",
    )
    listing.add_argument(
        "--category", metavar="ID", help="only this category id, e.g. dairy"
    )
    add_connection_options(listing, top=False)

    add = leaf(
        stock,
        "add",
        summary="add stock of a product, by name or id",
        description="Add stock. NAME is reused if a product has it (any case) and created\n"
        "otherwise; a new product needs --category. A NAME that is a UUID is\n"
        "sent as the product id. Expiry and location default from the product.",
        examples=[
            "kyokki stock add milk 1 l --category dairy",
            "kyokki stock add 'minced beef' 400 g --location freezer",
            "kyokki stock add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 6 pcs "
            "--expiry 2026-10-03",
        ],
        handler=commands.stock_add,
    )
    add.add_argument("name", metavar="NAME", help="product name, or product id")
    add.add_argument(
        "quantity",
        type=positive_number,
        metavar="QUANTITY",
        help="how much, in UNIT (a number above 0)",
    )
    add.add_argument(
        "unit",
        nargs="?",
        metavar="UNIT",
        help=f"{UNITS_HELP}; default: the product's own unit",
    )
    add.add_argument(
        "--category", metavar="ID", help="category id for a new product, e.g. dairy"
    )
    add.add_argument(
        "--location",
        choices=LOCATIONS,
        help="where it goes; default: the product's storage",
    )
    add.add_argument(
        "--expiry",
        type=iso_date,
        metavar="YYYY-MM-DD",
        help="expiry date; default: purchase date + shelf life",
    )
    add.add_argument(
        "--purchased",
        type=iso_date,
        metavar="YYYY-MM-DD",
        help="purchase date; default: today",
    )
    add_idempotency_option(add)
    add_connection_options(add, top=False)

    consume = leaf(
        stock,
        "consume",
        summary="use up an amount of a product, first to expire first",
        description="Consume AMOUNT UNIT of a product, taking from the item that expires\n"
        "first. NAME must match a product name exactly (any case); otherwise\n"
        "the candidates are printed and the exit code is 4. A NAME that is a\n"
        "UUID is sent as the product id.",
        examples=[
            "kyokki stock consume milk 2 dl",
            "kyokki stock consume 'minced beef' 0.4 kg --location freezer",
            "kyokki stock consume eggs 3 pcs --dry-run",
        ],
        handler=commands.stock_consume,
    )
    consume.add_argument("name", metavar="NAME", help="product name, or product id")
    consume.add_argument(
        "amount",
        type=positive_number,
        metavar="AMOUNT",
        help="how much, in UNIT (a number above 0)",
    )
    consume.add_argument("unit", metavar="UNIT", help=UNITS_HELP)
    consume.add_argument(
        "--location", choices=LOCATIONS, help="only items in this location"
    )
    consume.add_argument(
        "--allow-partial",
        action="store_true",
        help="consume what there is instead of failing on short stock (exit 5)",
    )
    consume.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be consumed; change nothing (no Idempotency-Key)",
    )
    add_idempotency_option(consume)
    add_connection_options(consume, top=False)

    # product
    product = group(
        top,
        "product",
        summary="resolve and teach product names",
        description="What a name means to Kyokki, and teaching it new ones.",
        examples=[
            "kyokki product resolve maito",
            "kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 maito",
        ],
    )

    resolve = leaf(
        product,
        "resolve",
        summary="what a name means: a match, candidates or a suggestion",
        description="Resolve a name: the product it names exactly (canonical or learned),\n"
        "else the closest candidates with a 0-1 score, and the normalised name\n"
        "to create when nothing matched. Never an error for no match.",
        examples=[
            "kyokki product resolve milk",
            "kyokki product resolve 'kevytmaito 1l' --json",
        ],
        handler=commands.product_resolve,
    )
    resolve.add_argument("name", metavar="NAME", help="the name to resolve")
    add_connection_options(resolve, top=False)

    names = product.add_parser(
        "name",
        help="the names a product answers to",
        description="The names a product answers to.",
        epilog=epilog(
            "kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 maito",
            "kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 'oat milk'",
        ),
        formatter_class=Formatter,
        allow_abbrev=False,
    )
    name_commands = names.add_subparsers(
        title="commands", dest="name_command", metavar="COMMAND", required=True
    )
    teach = leaf(
        name_commands,
        "add",
        summary="teach a product another name",
        description="Teach a product another name, as the cook's word. Afterwards stock\n"
        "consume and product resolve find the product by it. Exit 6 when the\n"
        "name already belongs to another product.",
        examples=[
            "kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 maito",
            "kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 'oat milk'",
        ],
        handler=commands.product_name_add,
    )
    teach.add_argument(
        "product_id",
        type=product_id,
        metavar="PRODUCT_ID",
        help="the product's id (a UUID), from product resolve or stock list --json",
    )
    teach.add_argument("name", metavar="NAME", help="the new name")
    add_idempotency_option(teach)
    add_connection_options(teach, top=False)

    # category
    category = group(
        top,
        "category",
        summary="the category ids for --category",
        description="Product categories.",
        examples=["kyokki category list", "kyokki category list --json"],
    )
    categories = leaf(
        category,
        "list",
        summary="every category: id, icon and name",
        description="Every category: its id (for --category), icon and name.",
        examples=["kyokki category list", "kyokki category list --json"],
        handler=commands.category_list,
    )
    add_connection_options(categories, top=False)

    return parser


# --- running ------------------------------------------------------------------


def secrets_in(argv: list[str]) -> list[str]:
    """Every token this run could know: the environment's and any --token value."""
    found = [os.environ.get("KYOKKI_TOKEN", "")]
    for i, arg in enumerate(argv):
        if arg == "--token" and i + 1 < len(argv):
            found.append(argv[i + 1])
        elif arg.startswith("--token="):
            found.append(arg.split("=", 1)[1])
    return [s for s in found if s]


def report(error: CliError, as_json: bool) -> None:
    detail = error.detail
    if as_json:
        output.print_json(detail)
        return
    if isinstance(detail, dict) and detail.get("candidates"):
        print(commands.candidates_table(detail["candidates"]))
    message = f"error: {error}"
    if isinstance(detail, dict):
        if detail.get("code") == "insufficient_stock":
            message += (
                f" (available: {output.number(detail.get('available'))} "
                f"{detail.get('unit', '')})"
            )
        if detail.get("code") == "conflict" and detail.get("product_name"):
            message += (
                f" (it names {detail['product_name']}, {detail.get('product_id')})"
            )
        if detail.get("hint"):
            message += f"\nhint: {detail['hint']}"
    output.note(message)


def run(argv: list[str], transport: httpx.BaseTransport | None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else USAGE

    as_json = output.wants_json(args.json)
    url = args.url or os.environ.get("KYOKKI_URL")
    token = args.token or os.environ.get("KYOKKI_TOKEN") or None
    if not url:
        output.note(
            "error: no Kyokki URL. Set KYOKKI_URL or pass --url, "
            "e.g. --url http://kyokki.lan:8000"
        )
        return USAGE
    if not url.startswith(("http://", "https://")):
        output.note(f"error: the URL must start with http:// or https://, got {url!r}")
        return USAGE

    key = getattr(args, "idempotency_key", None) or idempotency.derive_key(
        argv, idempotency.utc_now()
    )
    client = Api(url, token, transport=transport, verbose=args.verbose)
    try:
        outcome = args.handler(commands.Context(client, args, key))
    except CliError as error:
        report(error, as_json)
        return error.exit_code
    finally:
        client.close()

    if outcome.replayed:
        output.note("note: replayed the answer to an identical earlier request")
    if as_json:
        output.print_json(outcome.document)
    else:
        print(outcome.human())
    return api.OK


def main(
    argv: list[str] | None = None, transport: httpx.BaseTransport | None = None
) -> int:
    """The console script. ``transport`` lets the tests put a fake API underneath."""
    if argv is None:
        argv = sys.argv[1:]
    with output.redacted(secrets_in(argv)):
        return run(argv, transport)
