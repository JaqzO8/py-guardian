"""Puerta gratuita de convenciones para GitHub Actions, basada en el diff."""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys
import tomllib

from .checks import check_commit_messages, check_file, is_test_path
from .diffparse import parse_added_lines
from .models import FileChange, Finding

SNAKE = re.compile(r"^[a-z_][a-z0-9_]*$")
UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
HTTP_NAMES = {"request", "response", "flask", "fastapi", "starlette", "django"}
BUILTIN_BUSINESS_ERRORS = {"ValueError", "RuntimeError", "Exception"}


def load_policy(path: pathlib.Path) -> dict:
    """Carga las reglas versionadas; un archivo inválido falla de forma cerrada."""
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    if "policy" not in doc or "rules" not in doc:
        raise ValueError("guardian-policy.toml requiere [policy] y [rules]")
    return doc


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8")


def _changes(base: str, head: str) -> tuple[list[FileChange], list[str]]:
    raw = subprocess.check_output(
        ["git", "diff", "--name-status", "-z", base, head],
    ).decode("utf-8")
    fields = raw.split("\0")
    files = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        i += 1
        if status.startswith(("R", "C")):
            i += 1  # ruta anterior
        path = fields[i]
        i += 1
        if status.startswith("D"):
            continue
        patch = _git("diff", "--unified=0", "--no-ext-diff", base, head, "--", path)
        # El parser de diff usa únicamente cabeceras @@ y líneas +/-.
        patch = "\n".join(line for line in patch.splitlines()
                          if line.startswith(("@@ ", "+", "-", " "))
                          and not line.startswith(("+++ ", "--- ")))
        additions = len(parse_added_lines(patch))
        files.append(FileChange(path, "added" if status.startswith("A") else "modified",
                                patch, additions))
    messages = _git("log", "--format=%s", f"{base}..{head}").splitlines()
    return files, messages


def _finding(rule: str, message: str, path: str, line: int) -> Finding:
    return Finding(rule, "error", message, file=path, line=line)


def _check_python(path: str, source: str, added: set[int], policy: dict) -> list[Finding]:
    out = []
    forbidden = set(policy["policy"]["forbidden_names"])
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [_finding("python-syntax", "Sintaxis Python inválida.", path, exc.lineno or 1)]
    section = path.split("/")
    in_api = "api" in section
    in_service = "services" in section

    def _name_check(name: str, line: int, *, class_name: bool = False) -> None:
        if name in forbidden:
            out.append(_finding("meaningful-name", f"«{name}» no describe su propósito.", path, line))
        valid = PASCAL.fullmatch(name) if class_name else (SNAKE.fullmatch(name) or UPPER_SNAKE.fullmatch(name))
        if not valid:
            out.append(_finding("python-naming", f"Nombre «{name}» fuera de la convención.", path, line))

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if line not in added:
            continue
        if isinstance(node, ast.ClassDef):
            _name_check(node.name, line, class_name=True)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _name_check(node.name, line)
            params = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            for param in params:
                if param.arg not in {"self", "cls"}:
                    _name_check(param.arg, line)
            if not node.name.startswith("_"):
                if node.returns is None or any(a.annotation is None for a in params
                                               if a.arg not in {"self", "cls"}):
                    out.append(_finding("public-type-hints", "Función pública sin type hints completos.", path, line))
                if not ast.get_docstring(node):
                    out.append(_finding("public-docstring", "Función pública sin docstring.", path, line))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name):
                        _name_check(child.id, line)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.module if isinstance(node, ast.ImportFrom) else ""
            imports = [module, *(a.name for a in node.names)]
            if in_api and any("repositories" in item.split(".") for item in imports):
                out.append(_finding("api-layering", "La capa api no debe importar repositories.", path, line))
            if in_service and any(set(item.split(".")) & HTTP_NAMES for item in imports):
                out.append(_finding("service-http-coupling", "Un servicio no debe importar detalles HTTP.", path, line))
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                out.append(_finding("bare-except", "Usa una excepción específica en except.", path, line))
            if isinstance(node.type, ast.Name) and node.type.id == "Exception" and any(
                isinstance(stmt, ast.Pass) for stmt in node.body
            ):
                out.append(_finding("silent-except", "No silencies errores con except Exception: pass.", path, line))
        elif in_service and isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if isinstance(node.exc.func, ast.Name) and node.exc.func.id in BUILTIN_BUSINESS_ERRORS:
                out.append(_finding("business-error-type", "Usa una excepción de errors.py para errores de negocio.", path, line))
        elif in_service and isinstance(node, ast.Name) and node.id in {"request", "response"}:
            out.append(_finding("service-http-coupling", "Un servicio no debe depender de request/response HTTP.", path, line))
    return out


def review(files: list[FileChange], messages: list[str], sources: dict[str, str], policy: dict) -> list[Finding]:
    """Revisa cambios y devuelve fallos bloqueantes con ruta y línea."""
    p = policy["policy"]
    findings = check_commit_messages(messages)
    changed_tests = any(is_test_path(f.path) or any(f.path.startswith(root) for root in p["test_roots"])
                        for f in files)
    changed_source = False
    for f in files:
        findings += check_file(f, parse_added_lines(f.patch),
                               max_additions=p["max_added_lines_per_file"])
        production = any(f.path.startswith(root) for root in p["production_roots"])
        if production and f.path.endswith(".py") and not is_test_path(f.path):
            changed_source = True
            if f.path in sources:
                added = {line.number for line in parse_added_lines(f.patch)}
                findings += _check_python(f.path, sources[f.path], added, policy)
    if p["require_test_change_for_source"] and changed_source and not changed_tests:
        findings.append(Finding("tests-missing", "error", "Un cambio en código de producción debe incluir tests."))
    enabled = policy["rules"]
    for f in findings:
        f.severity = "error"  # Toda convención activada es obligatoria en el gate.
    return [f for f in findings if enabled.get(f.rule, True)]


def main() -> int:
    """Ejecuta la política sobre los commits del evento de GitHub."""
    parser = argparse.ArgumentParser(description="Valida el diff contra guardian-policy.toml")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    policy = load_policy(pathlib.Path("guardian-policy.toml"))
    files, messages = _changes(args.base, args.head)
    sources = {f.path: pathlib.Path(f.path).read_text(encoding="utf-8")
               for f in files if f.path.endswith(".py") and pathlib.Path(f.path).is_file()}
    findings = review(files, messages, sources, policy)
    for f in findings:
        location = f"{f.file}:{f.line or 1}" if f.file else "commit"
        sys.stdout.write(f"ERROR [{f.rule}] {location}: {f.message}\n")
    sys.stdout.write(f"Py Guardian: {len(files)} archivos revisados, {len(findings)} incumplimientos.\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
