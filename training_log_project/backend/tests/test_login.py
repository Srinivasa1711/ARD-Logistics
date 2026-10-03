import pytest


@pytest.mark.parametrize(
    "endpoint, role, redirect_path",
    [
        ("/login", "trainee", "/trainee_feedback_page"),
        ("/Trainerlogin", "trainer", "/Trainer_Form"),
    ],
)
def test_first_login_creates_user_with_route_role(
    client, auth_module, make_employee, endpoint, role, redirect_path
):
    make_employee()

    response = client.post(endpoint, data={"username": " Jane Doe ", "password": " E1001 "})

    assert response.status_code == 302
    assert response.headers["Location"].endswith(redirect_path)
    user = auth_module.User.query.filter_by(employee_id="E1001").one()
    assert user.role == role
    assert user.full_name == "Jane Doe"
    assert auth_module.check_password_hash(user.password_hash, "E1001")
    with client.session_transaction() as sess:
        assert sess["logged_in_username"] == "Jane Doe"
        assert sess["logged_in_employee_id"] == "E1001"
        assert sess["logged_in_user_role"] == role


def test_repeat_login_reuses_existing_user(client, auth_module, make_employee):
    make_employee()

    client.post("/login", data={"username": "Jane Doe", "password": "E1001"})
    client.post("/login", data={"username": "Jane Doe", "password": "E1001"})

    assert auth_module.User.query.filter_by(employee_id="E1001").count() == 1


def test_trainer_login_keeps_role_of_existing_trainee(client, auth_module, make_employee):
    make_employee()
    client.post("/login", data={"username": "Jane Doe", "password": "E1001"})

    client.post("/Trainerlogin", data={"username": "Jane Doe", "password": "E1001"})

    with client.session_transaction() as sess:
        assert sess["logged_in_user_role"] == "trainee"


@pytest.mark.parametrize(
    "endpoint, template",
    [
        ("/login", "Training_Form_Security.html"),
        ("/Trainerlogin", "Trainer_Form_Security.html"),
    ],
)
@pytest.mark.parametrize(
    "username, password",
    [
        ("Jane Doe", "WRONG"),
        ("John Doe", "E1001"),
        ("", ""),
    ],
)
def test_invalid_employee_login_is_rejected(
    client, auth_module, make_employee, rendered, endpoint, template, username, password
):
    make_employee()

    response = client.post(endpoint, data={"username": username, "password": password})

    assert response.status_code == 200
    assert rendered[-1] == {"template": template, "message": "Invalid username or password."}
    assert auth_module.User.query.count() == 0
    with client.session_transaction() as sess:
        assert "logged_in_user_role" not in sess


def test_admin_login_success(client, make_admin):
    make_admin()

    response = client.post(
        "/Adminlogin", data={"email": " Admin@ARDLogistics.com ", "password": "Secret123"}
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/Training_log_Admin_Dashboard")
    with client.session_transaction() as sess:
        assert sess["logged_in_user_role"] == "admin"


def test_admin_login_rejects_non_company_email(client, make_admin, rendered):
    make_admin(email="admin@gmail.com")

    client.post("/Adminlogin", data={"email": "admin@gmail.com", "password": "Secret123"})

    assert rendered[-1]["message"] == "Only @ardlogistics.com emails are allowed for admin accounts."
    with client.session_transaction() as sess:
        assert "logged_in_user_role" not in sess


@pytest.mark.parametrize(
    "admin_kwargs, password",
    [
        ({}, "WrongPass1"),
        ({"role": "trainer"}, "Secret123"),
        ({"password": None}, ""),
    ],
    ids=["wrong-password", "non-admin-role", "admin-without-password-set"],
)
def test_admin_login_rejected(client, make_admin, rendered, admin_kwargs, password):
    make_admin(**admin_kwargs)

    client.post("/Adminlogin", data={"email": "admin@ardlogistics.com", "password": password})

    assert rendered[-1] == {
        "template": "Admin_Form_Security.html",
        "message": "Invalid email or password.",
    }
    with client.session_transaction() as sess:
        assert "logged_in_user_role" not in sess


def test_create_admin_requires_company_email(client, auth_module):
    response = client.post("/create_admin", data={"email": "someone@gmail.com"})

    assert response.status_code == 400
    assert auth_module.User.query.count() == 0


def test_create_admin_rejects_duplicate_email(client, make_admin):
    make_admin()

    response = client.post("/create_admin", data={"email": "ADMIN@ardlogistics.com"})

    assert response.status_code == 400
    assert response.get_json()["message"] == "Email already exists"


def test_create_admin_creates_admin_without_usable_password(client, auth_module):
    response = client.post("/create_admin", data={"email": "New.Admin@ardlogistics.com"})

    assert response.get_json()["success"] is True
    user = auth_module.User.query.filter_by(email="new.admin@ardlogistics.com").one()
    assert user.role == "admin"
    assert user.password_hash == ""
