"""tests/test_routes.py – Integration tests for Flask routes."""


def test_login_page_loads(client):
    """Login page returns 200."""
    r = client.get("/login")
    assert r.status_code == 200
    assert b"AttendAI" in r.data


def test_login_redirect_unauthenticated(client):
    """Admin dashboard redirects to login when not authenticated."""
    r = client.get("/admin/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_invalid_login(client):
    """Invalid credentials show error flash."""
    r = client.post("/login", data={
        "username": "nobody",
        "password": "wrong"
    }, follow_redirects=True)
    assert b"Invalid username or password" in r.data


def test_admin_login_and_dashboard(client, db):
    """Valid admin login redirects to dashboard."""
    from database.models import User
    u = User(username="testadmin", email="ta@test.com", role="admin", is_active=True)
    u.set_password("Admin@123")
    db.session.add(u)
    db.session.commit()

    r = client.post("/login", data={
        "username": "testadmin",
        "password": "Admin@123"
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Dashboard" in r.data
