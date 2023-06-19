import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand

from organisations.models import Organisation, OrganisationRole
from projects.models import Project

user_model = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        user = None
        organisation = None
        project = None

        if should_create_user():
            user = user_model.objects.create_user(
                email=settings.DEFAULT_USER_EMAIL,
                password=settings.DEFAULT_USER_PASSWORD,
                is_superuser=settings.DEFAULT_USER_IS_SUPERUSER,
            )
            self.stdout.write(
                "Created default user with email %s", settings.DEFAULT_USER_EMAIL
            )

        if should_create_organisation():
            organisation = Organisation.objects.create(
                name=settings.DEFAULT_ORGANISATION_NAME
            )
            self.stdout.write(
                "Created default organisation with name %s",
                settings.DEFAULT_ORGANISATION_NAME,
            )

        if organisation and user:
            user.add_organisation(organisation, OrganisationRole.ADMIN)

        if should_create_project(organisation):
            project = Project.objects.create(
                name=settings.DEFAULT_PROJECT_NAME, organisation=organisation
            )
            self.stdout.write(
                "Created default project with name %s in organisation %s",
                settings.DEFAULT_PROJECT_NAME,
                settings.DEFAULT_ORGANISATION_NAME,
            )

        if user or organisation or project:
            self.stdout.write("Successfully initialised defaults.")


def should_create_user():
    return (
        settings.DEFAULT_USER_EMAIL
        and not user_model.objects.filter(email=settings.DEFAULT_USER_EMAIL).exists()
    )


def should_create_organisation():
    return (
        settings.DEFAULT_ORGANISATION_NAME
        and not Organisation.objects.filter(
            name=settings.DEFAULT_ORGANISATION_NAME
        ).exists()
    )


def should_create_project(organisation: Organisation):
    return (
        organisation is not None
        and settings.DEFAULT_PROJECT_NAME
        and not Project.objects.filter(
            name=settings.DEFAULT_PROJECT_NAME, organisation=organisation
        ).exists()
    )
