from datetime import datetime, timedelta

import pytest

GENERIC_MESSAGE = (
    "If an account with that email exists, a password reset link has been sent to your inbox."
)
INVALID_TOKEN_MESSAGE = "Invalid or expired reset token. Please request a new one."


@pytest.fixture
def admin_with_token(db, make_admin):
    admin = make_admin()
    admin.reset_token = "11111111-2222-3333-4444-555555555555"
    admin.reset_token_expiration = datetime.utcnow() + timedelta(minutes=30)
    db.session.commit()
    return admin


def test_request_reset_for_admin_issues_token_and_emails_link(
    client, auth_module, make_admin, rendered, sent_emails
):
    make_admin()
    before = datetime.utcnow()

    client.post("/request_password_reset", data={"email": " ADMIN@ardlogistics.com "})

    user = auth_module.User.query.filter_by(email="admin@ardlogistics.com").one()
    assert user.reset_token
    assert before + timedelta(minutes=59) < user.reset_token_expiration <= datetime.utcnow() + timedelta(hours=1)
    assert sent_emails == [
        ("admin@ardlogistics.com", f"http://localhost/reset_password/{user.reset_token}")
    ]
    assert rendered[-1]["message"] == GENERIC_MESSAGE
    assert rendered[-1]["reset_link"] is None


@pytest.mark.parametrize("role", ["trainee", "trainer"])
def test_request_reset_ignores_non_admin_accounts(
    client, auth_module, make_admin, rendered, sent_emails, role
):
    make_admin(role=role)

    client.post("/request_password_reset", data={"email": "admin@ardlogistics.com"})

    assert sent_emails == []
    assert auth_module.User.query.one().reset_token is None
    assert rendered[-1]["message"] == GENERIC_MESSAGE


def test_request_reset_for_unknown_email_does_not_reveal_existence(client, rendered, sent_emails):
    client.post("/request_password_reset", data={"email": "nobody@ardlogistics.com"})

    assert sent_emails == []
    assert rendered[-1]["message"] == GENERIC_MESSAGE


def test_reset_password_rejects_unknown_token(client, rendered):
    client.get("/reset_password/not-a-real-token")

    assert rendered[-1] == {
        "template": "reset_password.html",
        "message": INVALID_TOKEN_MESSAGE,
        "token": None,
    }


def test_reset_password_rejects_expired_token(client, db, admin_with_token, rendered):
    admin_with_token.reset_token_expiration = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()

    client.post(
        f"/reset_password/{admin_with_token.reset_token}",
        data={"new_password": "NewPass123", "confirm_new_password": "NewPass123"},
    )

    assert rendered[-1]["message"] == INVALID_TOKEN_MESSAGE


def test_reset_password_get_shows_form_for_valid_token(client, admin_with_token, rendered):
    client.get(f"/reset_password/{admin_with_token.reset_token}")

    assert rendered[-1] == {
        "template": "reset_password.html",
        "token": admin_with_token.reset_token,
        "message": None,
    }


@pytest.mark.parametrize(
    "new_password, confirm, message",
    [
        ("NewPass123", "NewPass124", "New passwords do not match."),
        ("Abc1234", "Abc1234", "Password must be at least 8 characters long and contain both letters and numbers."),
        ("abcdefgh", "abcdefgh", "Password must be at least 8 characters long and contain both letters and numbers."),
        ("12345678", "12345678", "Password must be at least 8 characters long and contain both letters and numbers."),
    ],
    ids=["mismatch", "too-short", "no-digits", "no-letters"],
)
def test_reset_password_validation_keeps_old_password(
    client, auth_module, admin_with_token, rendered, new_password, confirm, message
):
    token = admin_with_token.reset_token

    client.post(
        f"/reset_password/{token}",
        data={"new_password": new_password, "confirm_new_password": confirm},
    )

    assert rendered[-1]["message"] == message
    user = auth_module.User.query.filter_by(reset_token=token).one()
    assert auth_module.check_password_hash(user.password_hash, "Secret123")


def test_successful_reset_changes_password_and_consumes_token(
    client, auth_module, admin_with_token, rendered
):
    token = admin_with_token.reset_token

    client.post(
        f"/reset_password/{token}",
        data={"new_password": "NewPass123", "confirm_new_password": "NewPass123"},
    )

    assert rendered[-1]["success"] is True
    user = auth_module.User.query.filter_by(email="admin@ardlogistics.com").one()
    assert user.reset_token is None
    assert user.reset_token_expiration is None
    assert auth_module.check_password_hash(user.password_hash, "NewPass123")

    client.get(f"/reset_password/{token}")
    assert rendered[-1]["message"] == INVALID_TOKEN_MESSAGE

    old = client.post("/Adminlogin", data={"email": "admin@ardlogistics.com", "password": "Secret123"})
    assert old.status_code == 200
    new = client.post("/Adminlogin", data={"email": "admin@ardlogistics.com", "password": "NewPass123"})
    assert new.status_code == 302
