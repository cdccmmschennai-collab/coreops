"""API tests for the auth flow (login, logout, me) + throttling."""
from app.modules.users.models import UserRole


def test_login_success_returns_token(client, make_user):
    make_user("a@example.com", "password123", UserRole.admin)
    res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == 3600


def test_login_wrong_password_401(client, make_user):
    make_user("a@example.com", "password123")
    res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "nope"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_login_inactive_user_401(client, make_user):
    make_user("a@example.com", "password123", is_active=False)
    res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert res.status_code == 401


def test_login_email_is_case_insensitive(client, make_user):
    make_user("Mixed@Example.com", "password123")
    res = client.post("/api/v1/auth/login", json={"email": "mixed@example.com", "password": "password123"})
    assert res.status_code == 200


def test_me_returns_current_user(client, auth_header):
    headers = auth_header("me@example.com", role=UserRole.manager)
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "me@example.com"
    assert body["user"]["role"] == "manager"
    assert body["employee"] is None
    assert body["employee_id"] is None


def test_me_includes_linked_employee_id(client, make_user, make_employee, login):
    user = make_user("linked@example.com", "password123", UserRole.employee)
    emp = make_employee(employee_code="E-100", user_id=user.id)
    headers = login("linked@example.com")
    body = client.get("/api/v1/auth/me", headers=headers).json()
    assert body["employee_id"] == str(emp.id)


def test_me_without_token_401(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_logout_revokes_token(client, auth_header):
    headers = auth_header("x@example.com")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    # token is now denylisted
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_login_throttled_after_repeated_failures(client, make_user):
    make_user("t@example.com", "password123")
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "t@example.com", "password": "bad"})
    res = client.post("/api/v1/auth/login", json={"email": "t@example.com", "password": "password123"})
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"


def test_login_validation_error_422(client):
    res = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_error"
