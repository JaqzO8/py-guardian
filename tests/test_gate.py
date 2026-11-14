"""Pruebas de la puerta que se exige en GitHub antes de integrar cambios."""
from pathlib import Path

from guardian.gate import load_policy, review
from guardian.models import FileChange

POLICY = load_policy(Path(__file__).resolve().parents[1] / "guardian-policy.toml")


def test_gate_blocks_convention_violations_across_layers():
    api_source = "from app.repositories.user_repository import users\n"
    api = FileChange("app/api/users.py", "modified",
                     "@@ -0,0 +1 @@\n+from app.repositories.user_repository import users\n", 1)
    service_source = (
        "from flask import request\n"
        "def GetUser(data):\n"
        "    try:\n"
        "        return request.json\n"
        "    except:\n"
        "        raise ValueError('bad')\n"
    )
    service = FileChange("app/services/user_service.py", "modified",
                         "@@ -0,0 +1,6 @@\n" + "".join("+" + line + "\n" for line in service_source.splitlines()), 6)
    findings = review([api, service], ["bad message"],
                      {api.path: api_source, service.path: service_source}, POLICY)
    rules = {f.rule for f in findings}
    assert {"api-layering", "service-http-coupling", "python-naming", "meaningful-name",
            "bare-except", "business-error-type", "public-type-hints", "public-docstring",
            "tests-missing", "commit-conventional"} <= rules
    assert all(f.severity == "error" for f in findings)


def test_gate_accepts_compliant_source_with_tests():
    source = ('def get_user(user_id: int) -> int:\n'
              '    """Busca un usuario por ID."""\n'
              '    return user_id\n')
    code = FileChange("src/services/user_service.py", "added",
                      "@@ -0,0 +1,3 @@\n" + "".join("+" + line + "\n" for line in source.splitlines()), 3)
    test = FileChange("tests/test_user_service.py", "added", "@@ -0,0 +1 @@\n+assert True\n", 1)
    assert review([code, test], ["feat: agrega búsqueda"], {code.path: source}, POLICY) == []


def test_policy_can_disable_a_specific_rule():
    policy = {**POLICY, "rules": {**POLICY["rules"], "commit-conventional": False}}
    assert review([], ["bad message"], {}, policy) == []


def test_exception_and_name_rules_distinguish_valid_code():
    source = ('from app.errors import UserNotFound\n'
              'MAX_USERS = 10\n'
              'def get_user(user_id: int) -> int:\n'
              '    """Busca un usuario."""\n'
              '    if user_id > MAX_USERS:\n'
              '        raise UserNotFound(user_id)\n'
              '    return user_id\n')
    code = FileChange("app/services/user_service.py", "modified",
                      "@@ -0,0 +1,7 @@\n" + "".join("+" + line + "\n" for line in source.splitlines()), 7)
    test = FileChange("tests/test_user_service.py", "modified", "@@ -0,0 +1 @@\n+assert True\n", 1)
    assert review([code, test], ["fix: maneja usuario ausente"], {code.path: source}, POLICY) == []


def test_silent_exception_and_uppercase_function_are_blocked():
    source = ('def GET_USER(user_id: int) -> int:\n'
              '    """Busca un usuario."""\n'
              '    try:\n'
              '        return user_id\n'
              '    except Exception:\n'
              '        pass\n')
    code = FileChange("app/services/user_service.py", "modified",
                      "@@ -0,0 +1,6 @@\n" + "".join("+" + line + "\n" for line in source.splitlines()), 6)
    test = FileChange("tests/test_user_service.py", "modified", "@@ -0,0 +1 @@\n+assert True\n", 1)
    rules = {f.rule for f in review([code, test], ["fix: maneja errores"], {code.path: source}, POLICY)}
    assert {"python-naming", "silent-except"} <= rules
