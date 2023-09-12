import logging
import typing
from functools import reduce

from app_analytics.analytics_db_service import get_feature_evaluation_data
from app_analytics.influxdb_wrapper import get_multiple_event_list_for_feature
from core.constants import FLAGSMITH_UPDATED_AT_HEADER
from core.request_origin import RequestOrigin
from django.conf import settings
from django.core.cache import caches
from django.db.models import Q, QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import GenericAPIView, get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response

from app.pagination import CustomPagination
from environments.authentication import EnvironmentKeyAuthentication
from environments.identities.models import Identity
from environments.identities.serializers import (
    IdentityAllFeatureStatesSerializer,
)
from environments.models import Environment
from environments.permissions.permissions import (
    EnvironmentKeyPermissions,
    NestedEnvironmentPermissions,
)
from projects.models import Project
from projects.permissions import VIEW_PROJECT
from webhooks.webhooks import WebhookEventType

from .models import Feature, FeatureState
from .permissions import (
    CreateSegmentOverridePermissions,
    EnvironmentFeatureStatePermissions,
    FeaturePermissions,
    FeatureStatePermissions,
    IdentityFeatureStatePermissions,
)
from .serializers import (
    CreateSegmentOverrideFeatureStateSerializer,
    FeatureEvaluationDataSerializer,
    FeatureInfluxDataSerializer,
    FeatureOwnerInputSerializer,
    FeatureQuerySerializer,
    FeatureStateSerializerBasic,
    FeatureStateSerializerCreate,
    FeatureStateSerializerFull,
    FeatureStateSerializerWithIdentity,
    FeatureStateValueSerializer,
    GetInfluxDataQuerySerializer,
    GetUsageDataQuerySerializer,
    ListCreateFeatureSerializer,
    ProjectFeatureSerializer,
    SDKFeatureStateSerializer,
    SDKFeatureStatesQuerySerializer,
    UpdateFeatureSerializer,
    WritableNestedFeatureStateSerializer,
)
from .tasks import trigger_feature_state_change_webhooks

logger = logging.getLogger()
logger.setLevel(logging.INFO)

flags_cache = caches[settings.FLAGS_CACHE_LOCATION]


@swagger_auto_schema(responses={200: ListCreateFeatureSerializer()}, method="get")
@api_view(["GET"])
def get_feature_by_uuid(request, uuid):
    accessible_projects = request.user.get_permitted_projects(VIEW_PROJECT)
    qs = Feature.objects.filter(project__in=accessible_projects).prefetch_related(
        "multivariate_options", "owners", "tags"
    )
    feature = get_object_or_404(qs, uuid=uuid)
    serializer = ListCreateFeatureSerializer(instance=feature)
    return Response(serializer.data)


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(query_serializer=FeatureQuerySerializer()),
)
class FeatureViewSet(viewsets.ModelViewSet):
    permission_classes = [FeaturePermissions]
    pagination_class = CustomPagination

    def get_serializer_class(self):
        return {
            "list": ListCreateFeatureSerializer,
            "retrieve": ListCreateFeatureSerializer,
            "create": ListCreateFeatureSerializer,
            "update": UpdateFeatureSerializer,
            "partial_update": UpdateFeatureSerializer,
        }.get(self.action, ProjectFeatureSerializer)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Feature.objects.none()

        accessible_projects = self.request.user.get_permitted_projects(VIEW_PROJECT)

        project = get_object_or_404(accessible_projects, pk=self.kwargs["project_pk"])
        queryset = project.features.all().prefetch_related(
            "multivariate_options", "owners", "tags"
        )

        query_serializer = FeatureQuerySerializer(data=self.request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query_data = query_serializer.validated_data

        queryset = self._filter_queryset(queryset)

        sort = "%s%s" % (
            "-" if query_data["sort_direction"] == "DESC" else "",
            query_data["sort_field"],
        )
        queryset = queryset.order_by(sort)

        return queryset

    def perform_create(self, serializer):
        serializer.save(
            project_id=int(self.kwargs.get("project_pk")), user=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(project_id=self.kwargs.get("project_pk"))

    def perform_destroy(self, instance):
        feature_states = list(
            instance.feature_states.filter(identity=None, feature_segment=None)
        )
        self._trigger_feature_state_change_webhooks(feature_states)
        instance.delete()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.kwargs.get("project_pk"):
            context.update(
                project=get_object_or_404(
                    Project.objects.all(), pk=self.kwargs["project_pk"]
                ),
                user=self.request.user,
            )
        if self.action == "list" and "environment" in self.request.query_params:
            environment_id = self.request.query_params["environment"]
            context["overrides_data"] = Feature.get_overrides_data(environment_id)

        return context

    @swagger_auto_schema(
        request_body=FeatureOwnerInputSerializer,
        responses={200: ProjectFeatureSerializer},
    )
    @action(detail=True, methods=["POST"], url_path="add-owners")
    def add_owners(self, request, *args, **kwargs):
        serializer = FeatureOwnerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feature = self.get_object()
        serializer.add_owners(feature)
        return Response(self.get_serializer(instance=feature).data)

    @swagger_auto_schema(
        request_body=FeatureOwnerInputSerializer,
        responses={200: ProjectFeatureSerializer},
    )
    @action(detail=True, methods=["POST"], url_path="remove-owners")
    def remove_owners(self, request, *args, **kwargs):
        serializer = FeatureOwnerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feature = self.get_object()
        serializer.remove_users(feature)

        return Response(self.get_serializer(instance=feature).data)

    @swagger_auto_schema(
        query_serializer=GetInfluxDataQuerySerializer(),
        responses={200: FeatureInfluxDataSerializer()},
        deprecated=True,
        operation_description="Please use ​/api​/v1​/projects​/{project_pk}​/features​/{id}​/evaluation-data/",
    )
    @action(detail=True, methods=["GET"], url_path="influx-data")
    def get_influx_data(self, request, pk, project_pk):
        feature = get_object_or_404(Feature, pk=pk)

        query_serializer = GetInfluxDataQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        events_list = get_multiple_event_list_for_feature(
            feature_name=feature.name, **query_serializer.data
        )
        serializer = FeatureInfluxDataSerializer(instance={"events_list": events_list})
        return Response(serializer.data)

    @swagger_auto_schema(
        query_serializer=GetUsageDataQuerySerializer(),
        responses={200: FeatureEvaluationDataSerializer()},
    )
    @action(detail=True, methods=["GET"], url_path="evaluation-data")
    def get_evaluation_data(self, request, pk, project_pk):
        feature = get_object_or_404(Feature, pk=pk)

        query_serializer = GetUsageDataQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        usage_data = get_feature_evaluation_data(
            feature=feature, **query_serializer.data
        )
        serializer = FeatureEvaluationDataSerializer(usage_data, many=True)

        return Response(serializer.data)

    def _trigger_feature_state_change_webhooks(
        self, feature_states: typing.List[FeatureState]
    ):
        for feature_state in feature_states:
            trigger_feature_state_change_webhooks(
                feature_state, WebhookEventType.FLAG_DELETED
            )

    def _filter_queryset(self, queryset: QuerySet) -> QuerySet:
        query_serializer = FeatureQuerySerializer(data=self.request.query_params)
        query_serializer.is_valid(raise_exception=True)
        query_data = query_serializer.validated_data

        if query_data.get("search"):
            queryset = queryset.filter(name__icontains=query_data["search"])

        if "tags" in query_serializer.initial_data:
            if query_data.get("tags", "") == "":
                queryset = queryset.filter(tags__isnull=True)
            else:
                queryset = reduce(
                    lambda qs, tag_id: qs.filter(tags=tag_id),
                    query_data["tags"],
                    queryset,
                )

        if "is_archived" in query_serializer.initial_data:
            queryset = queryset.filter(is_archived=query_data["is_archived"])

        return queryset


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "feature",
                openapi.IN_QUERY,
                "ID of the feature to filter by.",
                required=False,
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "feature_name",
                openapi.IN_QUERY,
                "Name of the feature to filter by.",
                required=False,
                type=openapi.TYPE_STRING,
            ),
            openapi.Parameter(
                "anyIdentity",
                openapi.IN_QUERY,
                "Pass any value to get results that have an identity override. "
                "Do not pass for default behaviour.",
                required=False,
                type=openapi.TYPE_STRING,
            ),
        ]
    ),
)
class BaseFeatureStateViewSet(viewsets.ModelViewSet):
    """
    View set to manage feature states. Nested beneath environments and environments + identities
    to allow for filtering on both.
    """

    permission_classes = [IsAuthenticated, NestedEnvironmentPermissions]

    # Override serializer class to show correct information in docs
    def get_serializer_class(self):
        if self.action == "list":
            return FeatureStateSerializerWithIdentity
        elif self.action in ["retrieve", "update", "create"]:
            return FeatureStateSerializerBasic
        else:
            return FeatureStateSerializerCreate

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in ["update", "create"]:
            context["environment"] = self.get_environment_from_request()
        return context

    def get_queryset(self):
        """
        Override queryset to filter based on provided URL parameters.
        """
        if getattr(self, "swagger_fake_view", False):
            return FeatureState.objects.none()

        environment_api_key = self.kwargs["environment_api_key"]

        try:
            environment = Environment.objects.get(api_key=environment_api_key)
            queryset = FeatureState.get_environment_flags_queryset(
                environment_id=environment.id,
                feature_name=self.request.query_params.get("feature_name"),
            )
            queryset = self._apply_query_param_filters(queryset)

            if self.action == "list":
                queryset = queryset.prefetch_related(
                    "multivariate_feature_state_values"
                )

            return queryset.select_related("feature_state_value", "identity", "feature")
        except Environment.DoesNotExist:
            raise NotFound("Environment not found.")

    def _apply_query_param_filters(self, queryset: QuerySet) -> QuerySet:
        if self.request.query_params.get("feature"):
            queryset = queryset.filter(
                feature__id=int(self.request.query_params["feature"])
            )
        return queryset

    def get_environment_from_request(self):
        """
        Get environment object from URL parameters in request.
        """
        environment = Environment.objects.get(
            api_key=self.kwargs["environment_api_key"]
        )
        return environment

    def create(self, request, *args, **kwargs):
        """
        DEPRECATED: please use `/features/featurestates/` instead.
        Override create method to add environment and identity (if present) from URL parameters.
        """
        data = request.data
        if "feature" not in data:
            error = {"detail": "Feature not provided"}
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        environment = self.get_environment_from_request()
        data["environment"] = environment.id

        identity_pk = self.kwargs.get("identity_pk")
        if identity_pk:
            data["identity"] = identity_pk

        serializer = self.get_serializer(data=data)

        if serializer.is_valid(raise_exception=True):
            feature_state = serializer.save()
            headers = self.get_success_headers(serializer.data)

            if "feature_state_value" in data:
                self.update_feature_state_value(
                    data["feature_state_value"], feature_state
                )

            return Response(
                FeatureStateSerializerBasic(feature_state).data,
                status=status.HTTP_201_CREATED,
                headers=headers,
            )

    def update(self, request, *args, **kwargs):
        """
        Override update method to always assume update request is partial and create / update
        feature state value.
        """
        feature_state_to_update = self.get_object()
        feature_state_data = request.data

        # Check if feature state value was provided with request data. If so, create / update
        # feature state value object and associate with feature state.
        if "feature_state_value" in feature_state_data:
            feature_state_value = self.update_feature_state_value(
                feature_state_data["feature_state_value"], feature_state_to_update
            )

            if isinstance(feature_state_value, Response):
                return feature_state_value

            feature_state_data["feature_state_value"] = feature_state_value.id

        serializer = self.get_serializer(
            feature_state_to_update, data=feature_state_data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        if getattr(feature_state_to_update, "_prefetched_objects_cache", None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # refresh the instance from the database.
            feature_state_to_update = self.get_object()
            serializer = self.get_serializer(feature_state_to_update)

        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        Override partial_update as overridden update method assumes partial True for all requests.
        """
        return self.update(request, *args, **kwargs)

    def update_feature_state_value(self, value, feature_state):
        feature_state_value_dict = feature_state.generate_feature_state_value_data(
            value
        )

        if hasattr(feature_state, "feature_state_value"):
            feature_state_value_serializer = FeatureStateValueSerializer(
                instance=feature_state.feature_state_value,
                data=feature_state_value_dict,
            )
        else:
            data = {**feature_state_value_dict, "feature_state": feature_state.id}
            feature_state_value_serializer = FeatureStateValueSerializer(data=data)

        if feature_state_value_serializer.is_valid():
            feature_state_value = feature_state_value_serializer.save()
        else:
            return Response(
                feature_state_value_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return feature_state_value


class EnvironmentFeatureStateViewSet(BaseFeatureStateViewSet):
    permission_classes = [EnvironmentFeatureStatePermissions]

    def get_queryset(self):
        queryset = super().get_queryset().filter(feature_segment=None)
        if "anyIdentity" in self.request.query_params:
            # TODO: deprecate anyIdentity query parameter
            return queryset.exclude(identity=None)
        return queryset.filter(identity=None)

    def get_serializer_class(self):
        if self.action == "create_new_version":
            return FeatureStateSerializerBasic
        return super().get_serializer_class()


class IdentityFeatureStateViewSet(BaseFeatureStateViewSet):
    permission_classes = [IsAuthenticated, IdentityFeatureStatePermissions]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return FeatureState.objects.none()

        return super().get_queryset().filter(identity__pk=self.kwargs["identity_pk"])

    @action(methods=["GET"], detail=False)
    def all(self, request, *args, **kwargs):
        identity = get_object_or_404(Identity, pk=self.kwargs["identity_pk"])
        feature_states = identity.get_all_feature_states()

        serializer = IdentityAllFeatureStatesSerializer(
            instance=feature_states,
            many=True,
            context={
                "request": request,
                "identity": identity,
                "environment_api_key": identity.environment.api_key,
            },
        )

        return Response(serializer.data)


class SimpleFeatureStateViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = WritableNestedFeatureStateSerializer
    permission_classes = [FeatureStatePermissions]
    filterset_fields = ["environment", "feature", "feature_segment"]

    def get_queryset(self):
        if not self.action == "list":
            return FeatureState.objects.all()

        try:
            environment_id = self.request.query_params.get("environment")
            if not environment_id:
                raise ValidationError("'environment' GET parameter is required.")

            queryset = FeatureState.get_environment_flags_queryset(
                environment_id=environment_id
            )
            return queryset.select_related("feature_state_value").prefetch_related(
                "multivariate_feature_state_values"
            )
        except Environment.DoesNotExist:
            raise NotFound("Environment not found.")


@swagger_auto_schema(
    responses={200: WritableNestedFeatureStateSerializer()}, method="get"
)
@api_view(["GET"])
def get_feature_state_by_uuid(request, uuid):
    accessible_projects = request.user.get_permitted_projects(VIEW_PROJECT)
    qs = FeatureState.objects.filter(
        feature__project__in=accessible_projects
    ).select_related("feature_state_value")
    feature_state = get_object_or_404(qs, uuid=uuid)
    serializer = WritableNestedFeatureStateSerializer(instance=feature_state)
    return Response(serializer.data)


class SDKFeatureStates(GenericAPIView):
    serializer_class = SDKFeatureStateSerializer
    permission_classes = (EnvironmentKeyPermissions,)
    authentication_classes = (EnvironmentKeyAuthentication,)
    renderer_classes = [JSONRenderer]
    pagination_class = None

    @swagger_auto_schema(
        query_serializer=SDKFeatureStatesQuerySerializer(),
        responses={200: FeatureStateSerializerFull(many=True)},
    )
    @method_decorator(
        cache_page(
            timeout=settings.GET_FLAGS_ENDPOINT_CACHE_SECONDS,
            cache=settings.GET_FLAGS_ENDPOINT_CACHE_NAME,
        )
    )
    def get(self, request, identifier=None, *args, **kwargs):
        """
        USING THIS ENDPOINT WITH AN IDENTIFIER IS DEPRECATED.
        Please use `/identities/?identifier=<identifier>` instead.
        ---
        Note that when providing the `feature` query argument, this endpoint will
        return either a single object or a 404 (if the feature does not exist) rather
        than a list.
        """
        if identifier:
            return self._get_flags_response_with_identifier(request, identifier)

        if "feature" in request.GET:
            feature_states = FeatureState.get_environment_flags_list(
                environment_id=request.environment.id,
                feature_name=request.GET["feature"],
                additional_filters=self._additional_filters,
            )
            if len(feature_states) != 1:
                # TODO: what if more than one?
                return Response(
                    {"detail": "Given feature not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.get_serializer(feature_states[0]).data)

        if settings.CACHE_FLAGS_SECONDS > 0:
            data = self._get_flags_from_cache(request.environment)
        else:
            data = self.get_serializer(
                FeatureState.get_environment_flags_list(
                    environment_id=request.environment.id,
                    additional_filters=self._additional_filters,
                ),
                many=True,
            ).data

        updated_at = self.request.environment.updated_at
        return Response(
            data,
            headers={FLAGSMITH_UPDATED_AT_HEADER: updated_at.timestamp()},
        )

    @property
    def _additional_filters(self) -> Q:
        filters = Q(feature_segment=None, identity=None)

        if self.request.environment.get_hide_disabled_flags() is True:
            return filters & Q(enabled=True)

        if self.request.originated_from is RequestOrigin.CLIENT:
            return filters & Q(feature__is_server_key_only=False)

        return filters

    def _get_flags_from_cache(self, environment):
        data = flags_cache.get(environment.api_key)
        if not data:
            data = self.get_serializer(
                FeatureState.get_environment_flags_list(
                    environment_id=environment.id,
                    additional_filters=self._additional_filters,
                ),
                many=True,
            ).data
            flags_cache.set(environment.api_key, data, settings.CACHE_FLAGS_SECONDS)

        return data

    def _get_flags_response_with_identifier(self, request, identifier):
        identity, _ = Identity.objects.get_or_create(
            identifier=identifier, environment=request.environment
        )

        kwargs = {
            "identity": identity,
            "environment": request.environment,
            "feature_segment": None,
        }

        if "feature" in request.GET:
            kwargs["feature__name__iexact"] = request.GET["feature"]
            try:
                feature_state = identity.get_all_feature_states().get(
                    feature__name__iexact=kwargs["feature__name__iexact"],
                )
            except FeatureState.DoesNotExist:
                return Response(
                    {"detail": "Given feature not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(
                self.get_serializer(feature_state).data, status=status.HTTP_200_OK
            )

        flags = self.get_serializer(identity.get_all_feature_states(), many=True)
        return Response(flags.data, status=status.HTTP_200_OK)


def organisation_has_got_feature(request, organisation):
    """
    Helper method to set flag against organisation to confirm that they've requested their
    feature states for analytics purposes

    :param request: HTTP request
    :return: True if value set. None otherwise.
    """
    if organisation.has_requested_features:
        return None

    referer = request.META.get("HTTP_REFERER")
    if not referer or "bullet-train.io" in referer:
        return None
    else:
        organisation.has_requested_features = True
        organisation.save()
        return True


@swagger_auto_schema(
    method="POST",
    request_body=CreateSegmentOverrideFeatureStateSerializer(),
    responses={200: CreateSegmentOverrideFeatureStateSerializer()},
)
@permission_classes([CreateSegmentOverridePermissions()])
@api_view(["POST"])
def create_segment_override(
    request: Request, environment_api_key: str, feature_pk: int
):
    environment = get_object_or_404(Environment, api_key=environment_api_key)
    feature = get_object_or_404(Feature, project=environment.project, pk=feature_pk)

    serializer = CreateSegmentOverrideFeatureStateSerializer(
        data=request.data, context={"environment": environment, "feature": feature}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(environment=environment, feature=feature)
    return Response(serializer.data, status=201)
