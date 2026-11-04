from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass(frozen=True)
class Settings:
    model: str = "claude-sonnet-5-5"
    llm_mode: str = "anthropic"    # anthropic | simulated
    max_tokens: int = 1500
    max_files: int = 25              # tope de archivos enviados al LLM por push
    max_patch_chars: int = 12_000    # tope de caracteres de diff por archivo
    max_conventions_chars: int = 20_000
    max_findings_per_file: int = 10
    llm_blocking: bool = False       # False: los errores del LLM se degradan a warning
    llm_timeout: int = 60
    conventions_path: str = "CONVENTIONS.md"
    workers: int = 4

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            model=os.getenv("MODEL", d.model),
            llm_mode=os.getenv("LLM_MODE", d.llm_mode),
            max_tokens=int(os.getenv("MAX_TOKENS", d.max_tokens)),
            max_files=int(os.getenv("MAX_FILES", d.max_files)),
            max_patch_chars=int(os.getenv("MAX_PATCH_CHARS", d.max_patch_chars)),
            llm_blocking=_bool(os.getenv("LLM_BLOCKING"), d.llm_blocking),
            llm_timeout=int(os.getenv("LLM_TIMEOUT", d.llm_timeout)),
            conventions_path=os.getenv("CONVENTIONS_PATH", d.conventions_path),
            workers=int(os.getenv("WORKERS", d.workers)),
        )
