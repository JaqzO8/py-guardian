from __future__ import annotations

from dataclasses import dataclass, field

ERROR, WARNING, NOTICE = "error", "warning", "notice"
SEVERITIES = (ERROR, WARNING, NOTICE)


@dataclass(frozen=True)
class FileChange:
    path: str
    status: str          # added | modified | renamed | removed
    patch: str
    additions: int = 0


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None
    suggestion: str | None = None
    source: str = "check"   # check | llm


@dataclass
class Report:
    verdict: str                              # pass | pass_with_warnings | needs_changes
    findings: list[Finding] = field(default_factory=list)
    reviewed_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    llm_status: str = "skipped"               # ok | partial | failed | skipped
    discarded_llm_findings: int = 0
