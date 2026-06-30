"""Identifier-based login: email / employee_code / first_name, with ambiguous
first_name resolution (return selectable candidates instead of failing)."""
from app.modules.users.models import UserRole


def _login(client, identifier, password="password123"):
    return client.post(
        "/api/v1/auth/login", json={"identifier": identifier, "password": password}
    )


def test_login_with_email(client, make_user, make_employee):
    u = make_user("eve@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP001", first_name="Eve", last_name="A", user_id=u.id)
    assert _login(client, "eve@example.com").status_code == 200


def test_login_with_employee_code_case_insensitive(client, make_user, make_employee):
    u = make_user("c1@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP101", first_name="Siva", last_name="Kumar", user_id=u.id)
    res = _login(client, "emp101")  # lower-case on purpose
    assert res.status_code == 200, res.text


def test_login_with_unique_first_name_case_insensitive(client, make_user, make_employee):
    u = make_user("arjun@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP200", first_name="Arjun", last_name="Rao", user_id=u.id)
    res = _login(client, "ARJUN")  # different case
    assert res.status_code == 200, res.text


def test_ambiguous_first_name_returns_candidates(client, make_user, make_employee):
    u1 = make_user("siva1@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP101", first_name="Siva", last_name="Subramaniyan", user_id=u1.id)
    u2 = make_user("siva2@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP205", first_name="Siva", last_name="Kumar", user_id=u2.id)

    res = _login(client, "siva")
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["error"]["code"] == "ambiguous_identifier"
    candidates = body["error"]["details"]["candidates"]
    assert {c["employee_code"] for c in candidates} == {"EMP101", "EMP205"}
    assert {c["name"] for c in candidates} == {"Siva Subramaniyan", "Siva Kumar"}
    # No password is revealed and no token is issued.
    assert "access_token" not in body


def test_candidate_can_complete_login_with_employee_code(client, make_user, make_employee):
    u1 = make_user("siva1@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP101", first_name="Siva", last_name="Subramaniyan", user_id=u1.id)
    u2 = make_user("siva2@example.com", "secretpass9", UserRole.employee)
    make_employee(employee_code="EMP205", first_name="Siva", last_name="Kumar", user_id=u2.id)

    assert _login(client, "siva").status_code == 409
    # The user picks EMP205 and re-submits with their own password.
    res = _login(client, "EMP205", password="secretpass9")
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


def test_ambiguous_does_not_count_toward_throttle(client, make_user, make_employee):
    u1 = make_user("siva1@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP101", first_name="Siva", last_name="Subramaniyan", user_id=u1.id)
    u2 = make_user("siva2@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP205", first_name="Siva", last_name="Kumar", user_id=u2.id)
    # Repeated ambiguous attempts must keep returning 409, never 429.
    for _ in range(7):
        assert _login(client, "siva").status_code == 409


def test_unknown_identifier_is_generic_invalid(client):
    res = _login(client, "ghost")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_inactive_account_is_ignored(client, make_user, make_employee):
    u = make_user("bob@example.com", "password123", UserRole.employee, is_active=False)
    make_employee(employee_code="EMP300", first_name="Bob", last_name="Lee", user_id=u.id)
    # Neither the name nor the code resolves an inactive account.
    assert _login(client, "bob").status_code == 401
    assert _login(client, "EMP300").status_code == 401


def test_employee_without_login_is_ignored(client, make_employee):
    # Employee exists but has no linked user_id → cannot be a login target.
    make_employee(employee_code="EMP400", first_name="Carol", last_name="Diaz", user_id=None)
    assert _login(client, "carol").status_code == 401
    assert _login(client, "EMP400").status_code == 401


def test_name_collision_does_not_block_when_one_is_inactive(client, make_user, make_employee):
    # Two "Dan"s but only one usable account → resolves to a single login, not
    # an ambiguity (inactive accounts are filtered out before counting).
    active = make_user("dan_active@example.com", "password123", UserRole.employee)
    make_employee(employee_code="EMP501", first_name="Dan", last_name="One", user_id=active.id)
    inactive = make_user("dan_inactive@example.com", "password123", UserRole.employee, is_active=False)
    make_employee(employee_code="EMP502", first_name="Dan", last_name="Two", user_id=inactive.id)
    assert _login(client, "dan").status_code == 200
