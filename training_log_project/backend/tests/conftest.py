"""Test harness for Working_Training_Log_Authentication.py.

The module connects to SQL Server, starts a background scheduler and renders
templates from a folder Flask cannot see, all at import time. Before importing
it we stub ``pyodbc``, point Flask-SQLAlchemy at a temporary SQLite file and
disable the scheduler, so the real routes can run in isolation.
"""
import importlib
import os
import sys
import tempfile
import types
from unittest import mock

import flask_sqlalchemy
import pytest
from apscheduler.schedulers.background import BackgroundScheduler

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_NAME = "Working_Training_Log_Authentication"


def _fake_pyodbc():
    module = types.ModuleType("pyodbc")
    module.drivers = lambda: []

    def connect(*_args, **_kwargs):
        raise RuntimeError("pyodbc is stubbed out in tests")

    module.connect = connect
    return module


@pytest.fixture(scope="session")
def auth_module():
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(db_fd)
    original_init_app = flask_sqlalchemy.SQLAlchemy.init_app

    def init_app_with_sqlite(self, app):
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
        app.config["TESTING"] = True
        return original_init_app(self, app)

    sys.path.insert(0, BACKEND_DIR)
    with mock.patch.dict(sys.modules, {"pyodbc": _fake_pyodbc()}), \
            mock.patch.object(flask_sqlalchemy.SQLAlchemy, "init_app", init_app_with_sqlite), \
            mock.patch.object(BackgroundScheduler, "start", lambda self: None):
        module = importlib.import_module(MODULE_NAME)
    sys.path.remove(BACKEND_DIR)

    yield module

    sys.modules.pop(MODULE_NAME, None)
    os.remove(db_path)


@pytest.fixture
def rendered(auth_module, monkeypatch):
    """Replace render_template with a recorder: returns the template name and records its context."""
    calls = []

    def fake_render(template_name, **context):
        calls.append({"template": template_name, **context})
        return template_name

    monkeypatch.setattr(auth_module, "render_template", fake_render)
    return calls


@pytest.fixture
def sent_emails(auth_module, monkeypatch):
    emails = []
    monkeypatch.setattr(auth_module, "send_reset_email", lambda to, link: emails.append((to, link)))
    return emails


@pytest.fixture
def app(auth_module, rendered, sent_emails):
    flask_app = auth_module.app
    with flask_app.app_context():
        auth_module.db.drop_all()
        auth_module.db.create_all()
        yield flask_app
        auth_module.db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(auth_module, app):
    return auth_module.db


@pytest.fixture
def make_employee(auth_module, db):
    def _make(employee_id="E1001", first_name="Jane", last_name="Doe"):
        employee = auth_module.EmployeeInfo(
            employee_id=employee_id,
            first_name=first_name,
            last_name=last_name,
            full_name=f"{first_name} {last_name}",
        )
        db.session.add(employee)
        db.session.commit()
        return employee

    return _make


@pytest.fixture
def make_admin(auth_module, db):
    def _make(email="admin@ardlogistics.com", password="Secret123", role="admin"):
        user = auth_module.User(
            full_name=email.split("@")[0],
            employee_id=f"admin-{email}",
            email=email,
            role=role,
            password_hash=auth_module.generate_password_hash(password) if password else "",
        )
        db.session.add(user)
        db.session.commit()
        return user

    return _make


@pytest.fixture
def login_as(client):
    def _login(role, username="Jane Doe", employee_id="E1001"):
        with client.session_transaction() as sess:
            sess["logged_in_username"] = username
            sess["logged_in_employee_id"] = employee_id
            sess["logged_in_user_role"] = role

    return _login
