import pytest
from django.core.management import call_command
from pytest_django.fixtures import SettingsWrapper

from organisations.models import Organisation, UserOrganisation
from projects.models import Project
from users.models import FFAdminUser


@pytest.mark.parametrize(
    "user_email, user_password, user_is_superuser, organisation_name, project_name, "
    "expected_users, expected_organisations, expected_projects, expected_user_organisations",
    (
        (None, None, None, None, None, 0, 0, 0, 0),
        ("foo@bar.com", "foobar", False, None, None, 1, 0, 0, 0),
        ("foo@bar.com", "foobar", True, None, None, 1, 0, 0, 0),
        (None, None, None, "test org", None, 0, 1, 0, 0),
        (None, None, None, None, "test project", 0, 0, 0, 0),
        (None, None, None, "test org", "test project", 0, 1, 1, 0),
        ("foo@bar.com", "foobar", False, "test org", "test project", 1, 1, 1, 1),
    ),
)
def test_initdefaults(
    db: None,
    settings: SettingsWrapper,
    user_email: str,
    user_password: str,
    user_is_superuser: bool,
    organisation_name: str,
    project_name: str,
    expected_users: int,
    expected_organisations: int,
    expected_projects: int,
    expected_user_organisations: int,
) -> None:
    settings.DEFAULT_USER_EMAIL = user_email
    settings.DEFAULT_USER_PASSWORD = user_password
    settings.DEFAULT_USER_IS_SUPERUSER = user_is_superuser
    settings.DEFAULT_ORGANISATION_NAME = organisation_name
    settings.DEFAULT_PROJECT_NAME = project_name

    # When
    call_command("initdefaults")

    # Then
    user_queryset = FFAdminUser.objects.all()
    if user_is_superuser is not None:
        user_queryset = user_queryset.filter(is_superuser=user_is_superuser)
    assert user_queryset.count() == expected_users

    assert Organisation.objects.count() == expected_organisations
    assert Project.objects.count() == expected_projects
    assert UserOrganisation.objects.count() == expected_user_organisations


def test_initdefaults_does_nothing_if_entities_already_exist(
    db: None, settings: SettingsWrapper
) -> None:
    # Given
    email = "foo@bar.com"
    password = "foobar"
    is_superuser = True
    organisation_name = "test org"
    project_name = "test project"

    settings.DEFAULT_USER_EMAIL = email
    settings.DEFAULT_USER_PASSWORD = password
    settings.DEFAULT_USER_IS_SUPERUSER = is_superuser
    settings.DEFAULT_ORGANISATION_NAME = organisation_name
    settings.DEFAULT_PROJECT_NAME = project_name

    user = FFAdminUser.objects.create_user(
        email=email, password=password, is_superuser=is_superuser
    )
    organisation = Organisation.objects.create(name=organisation_name)
    Project.objects.create(name=project_name, organisation=organisation)
    user.add_organisation(organisation)

    # When
    call_command("initdefaults")

    # Then
    # no new entities were created
    assert FFAdminUser.objects.count() == 1
    assert Organisation.objects.count() == 1
    assert Project.objects.count() == 1
    assert UserOrganisation.objects.count() == 1
