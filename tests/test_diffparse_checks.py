from fixtures import BAD_COMMITS, BAD_FILE, CLEAN_FILE
from guardian.checks import check_commit_messages, run_checks
from guardian.diffparse import annotate_patch, is_reviewable, parse_added_lines


def test_added_line_numbers_follow_new_file():
    nums = [x.number for x in parse_added_lines(BAD_FILE.patch)]
    assert nums == [2, 3, 4, 5, 6, 7, 8, 9]


def test_removed_lines_do_not_shift_numbering():
    patch = "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
    assert [(x.number, x.text) for x in parse_added_lines(patch)] == [(2, "B")]


def test_annotate_marks_lines_and_truncates():
    text, cut = annotate_patch(BAD_FILE.patch, 10_000)
    assert "    4 + API_KEY" in text and not cut
    _, cut = annotate_patch(BAD_FILE.patch, 40)
    assert cut


def test_ignored_files():
    assert not is_reviewable("poetry.lock") and not is_reviewable("web/dist/app.js")
    assert not is_reviewable("assets/logo.png") and is_reviewable("src/app.py")


def test_conventional_commits():
    assert check_commit_messages(["feat(auth): agrega login", "Merge branch 'x'"]) == []
    assert check_commit_messages(BAD_COMMITS)[0].rule == "commit-conventional"


def test_bad_file_triggers_expected_rules():
    rules = {f.rule for f in run_checks([BAD_FILE], BAD_COMMITS)}
    assert {"secret-detected", "debug-leftover", "todo-without-ticket",
            "file-naming-snake-case", "commit-conventional"} <= rules


def test_secret_value_is_never_echoed():
    for f in run_checks([BAD_FILE], []):
        assert "abcdefghijklmnop" not in f.message


def test_fine_grained_github_token_is_blocked_without_echoing_it():
    from guardian.models import FileChange

    token = "github_" + "pat_" + "A" * 30
    patch = f"@@ -0,0 +1 @@\n+TOKEN = '{token}'\n"
    found = run_checks([FileChange("src/token_example.py", "modified", patch, 1)], [])
    assert any(f.rule == "secret-detected" for f in found)
    assert all(token not in f.message for f in found)


def test_clean_file_has_no_findings():
    assert run_checks([CLEAN_FILE], ["fix(core): corrige logger"]) == []


def test_ticketed_todo_and_test_files_are_allowed():
    from guardian.models import FileChange
    p = "@@ -0,0 +1,2 @@\n+# TODO(PROJ-12) migrar\n+print('ok en test')\n"
    assert run_checks([FileChange("tests/test_x.py", "added", p, 2)], []) == []
