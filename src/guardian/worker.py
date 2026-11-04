"""Lambda 2: trae el diff, corre verificaciones + agente y publica el resultado."""
from __future__ import annotations

import json
import logging
import os
import time

from . import agent, checks, metrics
from . import report as rpt
from .config import Settings
from .diffparse import is_reviewable
from .models import WARNING, Finding, Report

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def process(job: dict, *, gh, llm, settings: Settings) -> Report:
    repo, after = job["repo"], job["after"]
    gh.set_status(repo, after, "pending", "Revisando convenciones…")

    files, messages = gh.changed_files(repo, job.get("before", ""), after)
    files = [f for f in files if f.status != "removed"]
    reviewable = [f for f in files if is_reviewable(f.path) and f.patch]
    skipped = [f.path for f in files if f not in reviewable]

    findings: list[Finding] = checks.run_checks(reviewable, messages)

    # Los archivos más grandes primero; el resto queda listado como no revisado.
    ranked = sorted(reviewable, key=lambda f: f.additions, reverse=True)
    to_llm, over = ranked[: settings.max_files], ranked[settings.max_files:]
    skipped += [f.path for f in over]

    llm_status, discarded = "skipped", 0
    conventions = gh.get_file(repo, settings.conventions_path, after)
    if conventions is None:
        findings.append(Finding("conventions-missing", WARNING,
                                f"No existe {settings.conventions_path}; se omitió el análisis con IA."))
    elif llm is not None and to_llm:
        try:
            llm_findings, discarded, failed = agent.review_all(llm, conventions, to_llm, settings)
            findings += rpt.apply_llm_policy(llm_findings, settings.llm_blocking)
            if not failed:
                llm_status = "simulated" if isinstance(llm, agent.SimulatedClient) else "ok"
            else:
                llm_status = "partial" if len(failed) < len(to_llm) else "failed"
        except Exception:
            log.exception("el agente falló; se degrada a verificaciones deterministas")
            llm_status = "failed"

    result = Report(verdict=rpt.decide(findings), findings=findings,
                    reviewed_files=[f.path for f in reviewable], skipped_files=skipped,
                    llm_status=llm_status, discarded_llm_findings=discarded)
    state, desc = rpt.status_for(result)
    gh.comment_commit(repo, after, rpt.render_markdown(result, repo, after))
    gh.set_status(repo, after, state, desc)
    return result


def handler(event, context):
    from .github import GitHubClient
    from .secrets import get_secret
    from .store import Store

    settings = Settings.from_env()
    gh = GitHubClient(get_secret(os.environ["GITHUB_TOKEN_SECRET_ARN"]))
    if settings.llm_mode == "simulated":
        llm = agent.SimulatedClient()
    else:
        key = get_secret(os.environ["ANTHROPIC_KEY_SECRET_ARN"]).strip()
        llm = agent.AnthropicClient(key, settings) if key and key != "REPLACE_ME" else None
    store = Store(os.environ["TABLE_NAME"])

    failures = []
    for rec in event["Records"]:
        t0 = time.time()
        try:
            job = json.loads(rec["body"])
            r = process(job, gh=gh, llm=llm, settings=settings)
            counts = {s: sum(f.severity == s for f in r.findings) for s in ("error", "warning", "notice")}
            store.save_review(job["repo"], job["after"], r.verdict, counts)
            metrics.emit({"Reviews": 1, "Errors": counts["error"], "Warnings": counts["warning"],
                          "DiscardedLlmFindings": r.discarded_llm_findings,
                          "Blocked": int(r.verdict == "needs_changes"),
                          "LlmFailed": int(r.llm_status in ("failed", "partial"))},
                         {"Repo": job["repo"]})
            log.info(json.dumps({"event": "review_done", "repo": job["repo"], "sha": job["after"],
                                 "verdict": r.verdict, "ms": int((time.time() - t0) * 1000)}))
        except Exception:
            log.exception("revisión fallida; el mensaje volverá a la cola")
            failures.append({"itemIdentifier": rec["messageId"]})
    return {"batchItemFailures": failures}
