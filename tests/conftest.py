"""tests/conftest.py – Pytest fixtures for AttendAI."""

import pytest
from app import create_app
from database.models import db as _db


@pytest.fixture(scope="session")
def app():
    """Create test Flask application using isolated TestingConfig."""
    test_app = create_app("testing")
    return test_app


@pytest.fixture
def db(app):
    """Provides a clean in-memory database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app, db):
    """Provides test client with an initialized database."""
    return app.test_client()
