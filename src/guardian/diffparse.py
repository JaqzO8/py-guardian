"""Parseo de parches unificados de GitHub y filtro de archivos revisables."""
from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

IGNORED_PATTERNS = (
    "*.lock", "package-lock.json", "yarn.lock", "poetry.lock", "pnpm-lock.yaml",
    "*.min.js", "*.min.css", "*.map", "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif",
    "*.ico", "*.pdf", "*.zip", "*.woff", "*.woff2", "*_pb2.py", "*.generated.*",
    "dist/*", "*/dist/*", "build/*", "*/build/*", "vendor/*", "*/vendor/*",
    "node_modules/*", "*/node_modules/*", "*.snap",
)


@dataclass(frozen=True)
class AddedLine:
    number: int
    text: str


def is_reviewable(path: str) -> bool:
    base = posixpath.basename(path)
    return not any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(base, p)
                   for p in IGNORED_PATTERNS)


def _walk(patch: str):
    n = 0
    for raw in patch.splitlines():
        m = _HUNK.match(raw)
        if m:
            n = int(m.group(1))
            yield "hunk", None, raw
        elif raw.startswith("\\"):
            continue
        elif raw.startswith("+"):
            yield "add", n, raw[1:]
            n += 1
        elif raw.startswith("-"):
            yield "del", None, raw[1:]
        else:
            yield "ctx", n, raw[1:] if raw.startswith(" ") else raw
            n += 1


def parse_added_lines(patch: str) -> list[AddedLine]:
    return [AddedLine(n, t) for kind, n, t in _walk(patch) if kind == "add"]


def annotate_patch(patch: str, max_chars: int) -> tuple[str, bool]:
    """Devuelve el parche con numeración de líneas del archivo nuevo (para que el
    LLM cite líneas exactas) y un flag que indica si se truncó."""
    out: list[str] = []
    size = 0
    for kind, n, text in _walk(patch):
        if kind == "hunk":
            line = text
        elif kind == "add":
            line = f"{n:>5} + {text}"
        elif kind == "del":
            line = f"      - {text}"
        else:
            line = f"{n:>5}   {text}"
        size += len(line) + 1
        if size > max_chars:
            return "\n".join(out), True
        out.append(line)
    return "\n".join(out), False
