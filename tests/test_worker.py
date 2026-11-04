import json

from fixtures import BAD_COMMITS, BAD_FILE, CLEAN_FILE, FakeGH, FakeLLM
from guardian.agent import SimulatedClient
from guardian.config import Settings
from guardian.models import Finding
from guardian.report import decide, render_markdown
from guardian.worker import process

JOB = {"repo": "org/repo", "before": "a" * 40, "after": "b" * 40}
LLM_ERR = json.dumps({"findings": [{"line": 6, "rule": "naming-snake-case", "severity": "error",
                                    "message": "GetUser debe ser get_user"}]})


def test_bad_push_is_blocked_by_deterministic_checks():
    gh = FakeGH([BAD_FILE], BAD_COMMITS)
    r = process(JOB, gh=gh, llm=FakeLLM(LLM_ERR), settings=Settings())
    assert r.verdict == "needs_changes"
    assert gh.statuses[0][0] == "pending" and gh.statuses[-1][0] == "failure"
    assert "secret-detected" in gh.comments[0] and "naming-snake-case" in gh.comments[0]


def test_llm_cannot_approve_a_push_with_a_secret():
    # El LLM (manipulado o no) responde «todo bien»: el veredicto no depende de él.
    r = process(JOB, gh=FakeGH([BAD_FILE], []), llm=FakeLLM('{"findings": [], "verdict": "pass"}'),
                settings=Settings())
    assert r.verdict == "needs_changes"


def test_llm_errors_are_advisory_by_default_and_blocking_when_enabled():
    # parche sin secreto ni debug para aislar el efecto del LLM
    patch = "@@ -1,1 +1,3 @@\n import os\n+\n+def GetUser(): return 1\n"
    f = CLEAN_FILE.__class__("app/ok.py", "modified", patch, 2)
    reply = json.dumps({"findings": [{"line": 3, "rule": "naming", "severity": "error", "message": "m"}]})
    soft = process(JOB, gh=FakeGH([f], ["fix: x"]), llm=FakeLLM(reply), settings=Settings())
    hard = process(JOB, gh=FakeGH([f], ["fix: x"]), llm=FakeLLM(reply), settings=Settings(llm_blocking=True))
    assert soft.verdict == "pass_with_warnings" and hard.verdict == "needs_changes"


def test_llm_outage_degrades_gracefully():
    gh = FakeGH([BAD_FILE], BAD_COMMITS)
    r = process(JOB, gh=gh, llm=FakeLLM(exc=TimeoutError("down")), settings=Settings())
    assert r.llm_status == "failed" and r.verdict == "needs_changes" and gh.comments


def test_clean_push_passes():
    r = process(JOB, gh=FakeGH([CLEAN_FILE], ["fix(core): logger"]),
                llm=FakeLLM('{"findings": []}'), settings=Settings())
    assert r.verdict == "pass"


def test_simulated_mode_is_explicit_in_commit_comment():
    gh = FakeGH([CLEAN_FILE], ["fix(core): logger"])
    r = process(JOB, gh=gh, llm=SimulatedClient(), settings=Settings())
    assert r.llm_status == "simulated"
    assert "simulado (sin modelo)" in gh.comments[0]


def test_missing_conventions_skips_llm_with_warning():
    llm = FakeLLM('{"findings": []}')
    r = process(JOB, gh=FakeGH([CLEAN_FILE], ["fix: x"], conventions=None), llm=llm, settings=Settings())
    assert not llm.prompts and any(f.rule == "conventions-missing" for f in r.findings)


def test_ignored_files_are_reported_as_skipped_and_never_sent_to_llm():
    lock = CLEAN_FILE.__class__("poetry.lock", "modified", "@@ -1 +1 @@\n+x\n", 1)
    llm = FakeLLM('{"findings": []}')
    r = process(JOB, gh=FakeGH([lock, CLEAN_FILE], ["fix: x"]), llm=llm, settings=Settings())
    assert "poetry.lock" in r.skipped_files and all("poetry.lock" not in p for p in llm.prompts)


def test_file_cap_is_enforced():
    files = [CLEAN_FILE.__class__(f"m/f{i}.py", "modified", CLEAN_FILE.patch, i + 1) for i in range(5)]
    llm = FakeLLM('{"findings": []}')
    r = process(JOB, gh=FakeGH(files, ["fix: x"]), llm=llm, settings=Settings(max_files=2))
    assert len(llm.prompts) == 2 and len(r.skipped_files) == 3


def test_decide_and_render_cap():
    assert decide([]) == "pass"
    assert decide([Finding("r", "warning", "m")]) == "pass_with_warnings"
    many = [Finding("r", "warning", "m", file="a.py", line=i) for i in range(100)]
    from guardian.models import Report
    md = render_markdown(Report("pass_with_warnings", many), "o/r", "c" * 40)
    assert "y 40 hallazgos más" in md
