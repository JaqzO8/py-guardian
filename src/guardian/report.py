"""Decisión del veredicto (determinista) y render del comentario."""
from __future__ import annotations

from .models import ERROR, NOTICE, WARNING, Finding, Report

ICON = {ERROR: "❌", WARNING: "⚠️", NOTICE: "💡"}
HEADLINE = {"pass": "✅ Aprobado", "pass_with_warnings": "🟡 Aprobado con advertencias",
            "needs_changes": "❌ Requiere cambios"}
MAX_LISTED = 60


def apply_llm_policy(findings: list[Finding], llm_blocking: bool) -> list[Finding]:
    """Mientras el LLM no esté calibrado (llm_blocking=False) sus errores son
    advertencias: solo las verificaciones deterministas pueden bloquear."""
    if llm_blocking:
        return findings
    for f in findings:
        if f.source == "llm" and f.severity == ERROR:
            f.severity = WARNING
            f.message = f"[asesor] {f.message}"
    return findings


def decide(findings: list[Finding]) -> str:
    if any(f.severity == ERROR for f in findings):
        return "needs_changes"
    if any(f.severity == WARNING for f in findings):
        return "pass_with_warnings"
    return "pass"


def status_for(report: Report) -> tuple[str, str]:
    e = sum(f.severity == ERROR for f in report.findings)
    w = sum(f.severity == WARNING for f in report.findings)
    state = "failure" if report.verdict == "needs_changes" else "success"
    return state, f"{HEADLINE[report.verdict][2:].strip()} · errores: {e}, advertencias: {w}"


def render_markdown(report: Report, repo: str, sha: str) -> str:
    order = {ERROR: 0, WARNING: 1, NOTICE: 2}
    fs = sorted(report.findings, key=lambda f: (order.get(f.severity, 3), f.file or "", f.line or 0))
    counts = {s: sum(f.severity == s for f in fs) for s in (ERROR, WARNING, NOTICE)}
    lines = [f"## 🛡️ Py Guardian — {HEADLINE[report.verdict]}",
             f"`{sha[:7]}` · {len(report.reviewed_files)} archivos revisados · "
             f"errores: {counts[ERROR]} · advertencias: {counts[WARNING]} · "
             f"sugerencias: {counts[NOTICE]} · análisis IA: **{report.llm_status}**", ""]
    for f in fs[:MAX_LISTED]:
        where = ""
        if f.file:
            anchor = f"#L{f.line}" if f.line else ""
            label = f"{f.file}:{f.line}" if f.line else f.file
            where = f" [`{label}`](https://github.com/{repo}/blob/{sha}/{f.file}{anchor})"
        origin = "🤖" if f.source == "llm" else "🔧"
        lines.append(f"- {ICON.get(f.severity, '•')} {origin} **{f.rule}**{where} — {f.message}")
        if f.suggestion:
            lines.append(f"  - 💡 {f.suggestion}")
    if len(fs) > MAX_LISTED:
        lines.append(f"\n_… y {len(fs) - MAX_LISTED} hallazgos más._")
    if report.skipped_files:
        lines.append(f"\n<details><summary>{len(report.skipped_files)} archivos no revisados "
                     f"(ignorados o sobre el límite)</summary>\n\n"
                     + "\n".join(f"- `{p}`" for p in report.skipped_files[:50]) + "\n</details>")
    lines.append("\n<sub>🔧 verificación determinista · 🤖 análisis IA. "
                 "Las reglas viven en `CONVENTIONS.md`.</sub>")
    return "\n".join(lines)
