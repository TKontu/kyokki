"""Every `kyokki ...` command in the skill parses against the CLI's own parser.

Keeps `skills/kyokki/*.md` from drifting away from the CLI it documents: a renamed flag
or a dropped command shows up here as a parse failure, not silently in an agent's hands.
No HTTP happens; this only builds the argument parser and calls ``parse_args``.
"""

import re
import shlex
from pathlib import Path

import pytest

from kyokki import cli

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills" / "kyokki"

# A fenced-code-block line, or an inline `kyokki ...` span in prose.
FENCE = re.compile(r"^```")
INLINE_SPAN = re.compile(r"`(kyokki [^`]+)`")


def _commands_in(path: Path) -> list[str]:
    commands = []
    in_code_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if FENCE.match(stripped):
            in_code_block = not in_code_block
            continue
        if in_code_block and stripped.startswith("kyokki "):
            commands.append(stripped)
            continue
        for match in INLINE_SPAN.finditer(line):
            commands.append(match.group(1))
    return commands


def _all_commands() -> list[tuple[str, str]]:
    found = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        for command in _commands_in(path):
            found.append((path.name, command))
    return found


COMMANDS = _all_commands()


def test_the_skill_files_exist_and_have_commands() -> None:
    names = {name for name, _ in COMMANDS}
    assert names == {"SKILL.md", "examples.md"}
    assert len(COMMANDS) >= 10


@pytest.mark.parametrize(
    "entry",
    COMMANDS,
    ids=[f"{name}:{i}" for i, (name, _) in enumerate(COMMANDS)],
)
def test_skill_command_parses(entry: tuple[str, str]) -> None:
    name, line = entry
    argv = shlex.split(line)
    assert argv[0] == "kyokki", f"{name}: {line!r} does not start with kyokki"
    parser = cli.build_parser()
    try:
        parser.parse_args(argv[1:])
    except cli.UsageError as exc:
        pytest.fail(f"{name}: {line!r} does not parse: {exc}")
    except SystemExit as exc:
        # -h/--help exits 0 through argparse's own path, not our UsageError; any
        # other SystemExit would be a real parse problem.
        if exc.code not in (0, None):
            pytest.fail(f"{name}: {line!r} exited {exc.code}")
