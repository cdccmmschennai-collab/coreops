"""API tests for admin user management + role enforcement + guards."""
from app.modules.users.models import UserRole


def test_user_list_includes_linked_employee(client, auth_header, make_user, make_employee):
    """Users & Roles list exposes the linked employee (name + code), or null."""
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    linked_user = make_user("linked@example.com", role=UserRole.employee)
    make_employee(
        employee_code="EMP-LE1",
        first_name="Santhosh",
        last_name="Kumar",
        user_id=linked_user.id,
    )
    res = client.get("/api/v1/users", headers=headers)
    assert res.status_code == 200
    items = {u["email"]: u for u in res.json()["items"]}

    linked = items["linked@example.com"]
    assert linked["linked_employee"]["full_name"] == "Santhosh Kumar"
    assert linked["linked_employee"]["employee_code"] == "EMP-LE1"

    # The admin (no employee record) shows a null link.
    assert items["admin@example.com"]["linked_employee"] is None


def test_employee_cannot_list_users_403(client, auth_header):
    headers = auth_header("emp@example.com", role=UserRole.employee)
    assert client.get("/api/v1/users", headers=headers).status_code == 403


def test_admin_can_list_users(client, auth_header):
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.get("/api/v1/users", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert {"items", "total", "limit", "offset"} <= set(body)


def test_admin_creates_user_then_that_user_logs_in(client, auth_header):
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "new@example.com", "password": "password123", "role": "employee"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["role"] == "employee"
    login = client.post(
        "/api/v1/auth/login", json={"identifier": "new@example.com", "password": "password123"}
    )
    assert login.status_code == 200


def test_create_duplicate_email_409(client, auth_header):
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    payload = {"email": "dup@example.com", "password": "password123", "role": "employee"}
    assert client.post("/api/v1/users", headers=headers, json=payload).status_code == 201
    assert client.post("/api/v1/users", headers=headers, json=payload).status_code == 409


def test_set_password_then_login_with_new(client, auth_header, make_user):
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    target = make_user("p@example.com", "oldpassword")
    res = client.patch(
        f"/api/v1/users/{target.id}/password",
        headers=headers,
        json={"new_password": "brand-new-pw"},
    )
    assert res.status_code == 204
    assert client.post("/api/v1/auth/login", json={"identifier": "p@example.com", "password": "brand-new-pw"}).status_code == 200


def test_set_role(client, auth_header, make_user):
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    target = make_user("u@example.com", "password123", UserRole.employee)
    res = client.patch(f"/api/v1/users/{target.id}/role", headers=headers, json={"role": "manager"})
    assert res.status_code == 200
    assert res.json()["role"] == "manager"


def test_cannot_demote_last_admin(client, auth_header):
    # auth_header creates the only admin and logs them in
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    me = client.get("/api/v1/auth/me", headers=headers).json()["user"]
    res = client.patch(f"/api/v1/users/{me['id']}/role", headers=headers, json={"role": "employee"})
    assert res.status_code == 409


def test_get_unknown_user_404(client, auth_header):
    headers = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.get("/api/v1/users/00000000-0000-0000-0000-000000000000", headers=headers)
    assert res.status_code == 404
