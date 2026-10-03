import pytest

ROLE_GATED_PAGES = [
    ("/Training_log_Admin_Dashboard", "admin"),
    ("/trainee_feedback_page", "trainee"),
    ("/feedback_page/some-uuid", "trainer"),
]
ALL_ROLES = ["admin", "trainer", "trainee"]


@pytest.mark.parametrize("path, allowed_role", ROLE_GATED_PAGES)
def test_role_gated_pages_deny_anonymous(client, path, allowed_role):
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("path, allowed_role", ROLE_GATED_PAGES)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_role_gated_pages_only_allow_their_role(client, login_as, path, allowed_role, role):
    login_as(role)

    expected = 200 if role == allowed_role else 403
    assert client.get(path).status_code == expected


@pytest.mark.parametrize(
    "path",
    ["/submit_trainee_feedback", "/submit_trainer_form", "/submit_feedback"],
)
def test_form_submissions_require_login(client, auth_module, path):
    response = client.post(path, json={"overall_feedback_text": "x"})

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "message": "Unauthorized"}
    assert auth_module.TraineeFeedbackSubmission.query.count() == 0
    assert auth_module.TrainerFormSubmission.query.count() == 0
    assert auth_module.FeedbackSubmission.query.count() == 0
