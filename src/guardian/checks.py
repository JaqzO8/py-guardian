"""Verificaciones deterministas: baratas, reproducibles y las únicas que pueden
bloquear por sí solas. El LLM complementa, no reemplaza, estas reglas."""
from __future__ import annotations

import posixpath
import re

from .diffparse import AddedLine, parse_added_lines
from .models import ERROR, WARNING, FileChange, Finding

CONVENTIONAL_COMMIT = re.compile(
    r"^(feat|fix|docs|refactor|test|chore)"
    r"(\([\w\-./]+\))?!?: \S.{0,70}$"
)
SNAKE_PY = re.compile(r"^[a-z_][a-z0-9_]*\.py$")
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$"
)
SECRET_PATTERNS = {
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "clave privada": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "token de GitHub": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "clave de Anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "credencial literal": re.compile(
        r"""(?i)\b(api[_-]?key|secret|passw(?:or)?d|token)\b\s*[:=]\s*['"][^'"\s]{8,}['"]"""
    ),
}
DEBUG_PY = re.compile(r"^\s*(print\(|breakpoint\(\)|import pdb|pdb\.set_trace\(\))")
DEBUG_JS = re.compile(r"^\s*(console\.log\(|debugger\b)")
TODO_NO_TICKET = re.compile(r"\b(TODO|FIXME)\b(?!\(?[A-Z][A-Z0-9]+-\d+)")
MAX_ADDITIONS_PER_FILE = 500


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def check_commit_messages(messages: list[str]) -> list[Finding]:
    out = []
    for msg in messages:
        first = msg.splitlines()[0].strip() if msg.strip() else ""
        if first.startswith("Merge "):
            continue
        if not CONVENTIONAL_COMMIT.match(first):
            out.append(Finding(
                rule="commit-conventional", severity=WARNING,
                message=f"El commit «{first[:60]}» no sigue Conventional Commits.",
                suggestion="Usa el formato: tipo(ámbito): descripción. Ej.: feat(auth): agrega login",
            ))
    return out


def check_file(change: FileChange, added: list[AddedLine],
               max_additions: int = MAX_ADDITIONS_PER_FILE) -> list[Finding]:
    """Revisa las líneas añadidas y el nombre de un archivo cambiado."""
    out: list[Finding] = []
    path = change.path
    ext = posixpath.splitext(path)[1]
    base = posixpath.basename(path)
    is_test = is_test_path(path)

    if ext == ".py" and not is_test and base != "__init__.py" and not SNAKE_PY.match(base):
        out.append(Finding("file-naming-snake-case", WARNING,
                           f"El archivo «{base}» debe usar snake_case.", file=path))

    if change.additions > max_additions:
        out.append(Finding("pr-size", WARNING,
                           f"{change.additions} líneas añadidas en un archivo; divide el cambio.",
                           file=path))

    for line in added:
        for label, rx in SECRET_PATTERNS.items():
            if rx.search(line.text):
                out.append(Finding(
                    "secret-detected", ERROR,
                    f"Posible {label} en el código. Rótala y muévela a un gestor de secretos.",
                    file=path, line=line.number))
                break
        if not is_test:
            rx = DEBUG_PY if ext == ".py" else DEBUG_JS if ext in {".js", ".ts", ".jsx", ".tsx"} else None
            if rx and rx.search(line.text):
                out.append(Finding("debug-leftover", WARNING,
                                   "Código de depuración olvidado; usa el logger del proyecto.",
                                   file=path, line=line.number))
        if ext in {".py", ".js", ".jsx", ".ts", ".tsx"} and TODO_NO_TICKET.search(line.text):
            out.append(Finding("todo-without-ticket", WARNING,
                               "TODO/FIXME sin ticket asociado (ej.: TODO(PROJ-123)).",
                               file=path, line=line.number))
    return out


def check_missing_tests(files: list[FileChange]) -> list[Finding]:
    code_added = [f for f in files
                  if f.status == "added" and f.additions >= 10
                  and posixpath.splitext(f.path)[1] in {".py", ".js", ".ts", ".tsx", ".jsx"}
                  and not is_test_path(f.path) and posixpath.basename(f.path) != "__init__.py"]
    if code_added and not any(is_test_path(f.path) for f in files):
        names = ", ".join(f.path for f in code_added[:3])
        return [Finding("tests-missing", WARNING,
                        f"Se añadió código nuevo ({names}) sin ningún test en el push.")]
    return []


def run_checks(files: list[FileChange], commit_messages: list[str]) -> list[Finding]:
    findings = check_commit_messages(commit_messages)
    for f in files:
        findings += check_file(f, parse_added_lines(f.patch))
    findings += check_missing_tests(files)
    return findings
