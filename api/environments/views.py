# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from django.db.models import Count
from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from environments.permissions.permissions import (
    EnvironmentAdminPermission,
    EnvironmentPermissions,
    NestedEnvironmentPermissions,
)
from permissions.permissions_calculator import get_environment_permission_data
from permissions.serializers import (
    PermissionModelSerializer,
    UserObjectPermissionsSerializer,
)
from projects.models import Project
from webhooks.mixins import TriggerSampleWebhookMixin
from webhooks.webhooks import WebhookType

from .identities.traits.models import Trait
from .identities.traits.serializers import (
    DeleteAllTraitKeysSerializer,
    TraitKeysSerializer,
)
from .models import Environment, EnvironmentAPIKey, Webhook
from .permissions.models import (
    EnvironmentPermissionModel,
    UserEnvironmentPermission,
)
from .serializers import (
    CloneEnvironmentSerializer,
    CreateUpdateEnvironmentSerializer,
    EnvironmentAPIKeySerializer,
    EnvironmentRetrieveSerializerWithMetadata,
    EnvironmentSerializerWithMetadata,
    WebhookSerializer,
)

logger = logging.getLogger(__name__)


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "project",
                openapi.IN_QUERY,
                "ID of the project to filter by.",
                required=False,
                type=openapi.TYPE_INTEGER,
            )
        ]
    ),
)
class EnvironmentViewSet(viewsets.ModelViewSet):
    lookup_field = "api_key"
    permission_classes = [EnvironmentPermissions]

    def get_serializer_class(self):
        if self.action == "trait_keys":
            return TraitKeysSerializer
        if self.action == "delete_traits":
            return DeleteAllTraitKeysSerializer
        if self.action == "clone":
            return CloneEnvironmentSerializer
        if self.action == "retrieve":
            return EnvironmentRetrieveSerializerWithMetadata
        elif self.action in ("create", "update", "partial_update"):
            return CreateUpdateEnvironmentSerializer
        return EnvironmentSerializerWithMetadata

    def get_serializer_context(self):
        context = super(EnvironmentViewSet, self).get_serializer_context()
        if self.kwargs.get("api_key"):
            context["environment"] = self.get_object()
        return context

    def get_queryset(self):
        if self.action == "list":
            project_id = self.request.query_params.get(
                "project"
            ) or self.request.data.get("project")

            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                raise ValidationError("Invalid or missing value for project parameter.")

            return self.request.user.get_permitted_environments(
                "VIEW_ENVIRONMENT", project=project
            )

        # Permission class handles validation of permissions for other actions
        queryset = Environment.objects.all()

        if self.action == "retrieve":
            queryset = queryset.annotate(
                total_segment_overrides=Count("feature_segments")
            )

        return queryset

    def perform_create(self, serializer):
        environment = serializer.save()
        if getattr(self.request.user, "is_master_api_key_user", False) is False:
            UserEnvironmentPermission.objects.create(
                user=self.request.user, environment=environment, admin=True
            )

    @action(detail=True, methods=["GET"], url_path="trait-keys")
    def trait_keys(self, request, *args, **kwargs):
        keys = [
            trait_key
            for trait_key in Trait.objects.filter(
                identity__environment=self.get_object()
            )
            .order_by()
            .values_list("trait_key", flat=True)
            .distinct()
        ]

        data = {"keys": keys}

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(
                {"detail": "Couldn't get trait keys"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["POST"])
    def clone(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        clone = serializer.save(source_env=self.get_object())

        if getattr(request.user, "is_master_api_key_user", False) is False:
            UserEnvironmentPermission.objects.create(
                user=self.request.user, environment=clone, admin=True
            )

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["POST"], url_path="delete-traits")
    def delete_traits(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.delete()
            return Response(status=status.HTTP_200_OK)
        else:
            return Response(
                {"detail": "Couldn't delete trait keys."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @swagger_auto_schema(responses={200: PermissionModelSerializer})
    @action(detail=False, methods=["GET"])
    def permissions(self, *args, **kwargs):
        return Response(
            PermissionModelSerializer(
                instance=EnvironmentPermissionModel.objects.all(), many=True
            ).data
        )

    @swagger_auto_schema(responses={200: UserObjectPermissionsSerializer})
    @action(
        detail=True,
        methods=["GET"],
        url_path="my-permissions",
        url_name="my-permissions",
    )
    def user_permissions(self, request, *args, **kwargs):
        if getattr(request.user, "is_master_api_key_user", False) is True:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    "detail": "This endpoint can only be used with a user and not Master API Key"
                },
            )

        environment = self.get_object()

        permission_data = get_environment_permission_data(
            environment=environment, user=request.user
        )
        serializer = UserObjectPermissionsSerializer(instance=permission_data)
        return Response(serializer.data)

    @action(detail=True, methods=["GET"], url_path="document")
    def get_document(self, request, api_key: str):
        return Response(Environment.get_environment_document(api_key))


class NestedEnvironmentViewSet(viewsets.GenericViewSet):
    model_class = None
    webhook_type = WebhookType.ENVIRONMENT

    def get_queryset(self):
        return self.model_class.objects.filter(
            environment__api_key=self.kwargs.get("environment_api_key")
        )

    def perform_create(self, serializer):
        serializer.save(environment=self._get_environment())

    def perform_update(self, serializer):
        serializer.save(environment=self._get_environment())

    def _get_environment(self):
        return Environment.objects.get(api_key=self.kwargs.get("environment_api_key"))


class WebhookViewSet(
    NestedEnvironmentViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    TriggerSampleWebhookMixin,
):
    serializer_class = WebhookSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, NestedEnvironmentPermissions]
    model_class = Webhook

    webhook_type = WebhookType.ENVIRONMENT


class EnvironmentAPIKeyViewSet(
    NestedEnvironmentViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
):
    serializer_class = EnvironmentAPIKeySerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, EnvironmentAdminPermission]
    model_class = EnvironmentAPIKey
