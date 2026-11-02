"""Demo local de punta a punta, sin AWS ni GitHub.

  python scripts/demo_local.py                 # LLM simulado (sin red)
  ANTHROPIC_API_KEY=sk-... python scripts/demo_local.py   # LLM real
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from fixtures import BAD_COMMITS, BAD_FILE, FakeGH, FakeLLM  # noqa: E402

from guardian.agent import AnthropicClient  # noqa: E402
from guardian.config import Settings  # noqa: E402
from guardian.worker import process  # noqa: E402

settings = Settings.from_env()
key = os.getenv("ANTHROPIC_API_KEY")
if key:
    llm = AnthropicClient(key, settings)
    print(f"[LLM real: {settings.model}]\n")
else:
    llm = FakeLLM(json.dumps({"findings": [
        {"line": 6, "rule": "naming-snake-case", "severity": "error",
         "message": "La función `GetUser` debe llamarse `get_user` (snake_case).",
         "suggestion": "def get_user(user_id: int) -> User:"},
        {"line": 9, "rule": "layering", "severity": "warning",
         "message": "El servicio consulta `db` directamente; debe pasar por `repositories/`.",
         "suggestion": "return user_repository.find_by_id(user_id)"},
        {"line": 400, "rule": "alucinada", "severity": "error", "message": "línea inexistente"},
    ]}))
    print("[LLM simulado: sin red]\n")

gh = FakeGH([BAD_FILE], BAD_COMMITS, (ROOT / "CONVENTIONS.md").read_text())
report = process({"repo": "acme/shop", "before": "a" * 40, "after": "c0ffee" + "0" * 34},
                 gh=gh, llm=llm, settings=settings)
print("Estados enviados a GitHub:", gh.statuses, "\n")
print(gh.comments[0])
print(f"\nVeredicto: {report.verdict} | hallazgos descartados por validación: {report.discarded_llm_findings}")
