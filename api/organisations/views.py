# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
from datetime import datetime

from app_analytics.influxdb_wrapper import (
    get_events_for_organisation,
    get_multiple_event_list_for_organisation,
)
from django.contrib.sites.shortcuts import get_current_site
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import action, api_view, authentication_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from organisations.exceptions import (
    OrganisationHasNoSubscription,
    SubscriptionNotFound,
)
from organisations.models import (
    Organisation,
    OrganisationRole,
    OrganisationSubscriptionInformationCache,
    OrganisationWebhook,
    Subscription,
)
from organisations.permissions.models import OrganisationPermissionModel
from organisations.permissions.permissions import (
    NestedOrganisationEntityPermission,
    OrganisationPermission,
)
from organisations.serializers import (
    GetHostedPageForSubscriptionUpgradeSerializer,
    InfluxDataQuerySerializer,
    InfluxDataSerializer,
    MultiInvitesSerializer,
    OrganisationSerializerFull,
    OrganisationWebhookSerializer,
    PortalUrlSerializer,
    SubscriptionDetailsSerializer,
    UpdateSubscriptionSerializer,
)
from permissions.permissions_calculator import get_organisation_permission_data
from permissions.serializers import (
    PermissionModelSerializer,
    UserObjectPermissionsSerializer,
)
from projects.serializers import ProjectListSerializer
from users.serializers import UserIdSerializer
from webhooks.mixins import TriggerSampleWebhookMixin
from webhooks.webhooks import WebhookType

from .chargebee import extract_subscription_metadata

logger = logging.getLogger(__name__)


class OrganisationViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, OrganisationPermission)

    def get_serializer_class(self):
        if self.action == "remove_users":
            return UserIdSerializer
        elif self.action == "invite":
            return MultiInvitesSerializer
        elif self.action == "update_subscription":
            return UpdateSubscriptionSerializer
        elif self.action == "get_portal_url":
            return PortalUrlSerializer
        elif self.action == "get_influx_data":
            return InfluxDataSerializer
        elif self.action == "get_hosted_page_url_for_subscription_upgrade":
            return GetHostedPageForSubscriptionUpgradeSerializer
        elif self.action == "permissions":
            return PermissionModelSerializer
        elif self.action == "my_permissions":
            return UserObjectPermissionsSerializer
        elif self.action == "get_subscription_metadata":
            return SubscriptionDetailsSerializer
        return OrganisationSerializerFull

    def get_serializer_context(self):
        context = super(OrganisationViewSet, self).get_serializer_context()
        if self.action in ("remove_users", "invite", "update_subscription"):
            context["organisation"] = self.kwargs.get("pk")
        return context

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organisation.objects.none()
        return self.request.user.organisations.all()

    def get_throttles(self):
        if self.action == "invite":
            # since there is no way to set the throttle scope on an action,
            # we set it for each request here.
            self.throttle_scope = "invite"
            return [ScopedRateThrottle()]
        return super(OrganisationViewSet, self).get_throttles()

    def create(self, request, **kwargs):
        """
        Override create method to add new organisation to authenticated user
        """
        user = request.user
        serializer = OrganisationSerializerFull(data=request.data)
        if serializer.is_valid():
            org = serializer.save()
            user.add_organisation(org, OrganisationRole.ADMIN)

            return Response(serializer.data, status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, permission_classes=[IsAuthenticated])
    def projects(self, request, pk):
        organisation = self.get_object()
        projects = organisation.projects.all()
        return Response(ProjectListSerializer(projects, many=True).data)

    @action(detail=True, methods=["POST"])
    def invite(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # serializer returns a dictionary containing the list of serialized invite objects since it's a single
        # serializer generating multiple instances.
        return Response(serializer.data.get("invites"), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["POST"], url_path="remove-users")
    def remove_users(self, request, pk):
        """
        Takes a list of users and removes them from the organisation provided in the url
        """
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=200)

    @swagger_auto_schema(
        deprecated=True,
        operation_description="Please use ​​/api​/v1​/organisations​/{organisation_pk}​/usage-data​/total-count​/",
    )
    @action(
        detail=True,
        methods=["GET"],
    )
    def usage(self, request, pk):
        organisation = self.get_object()
        try:
            events = get_events_for_organisation(organisation.id)
        except (TypeError, ValueError):
            # TypeError can be thrown when getting service account if not configured
            # ValueError can be thrown if GA returns a value that cannot be converted to integer
            return Response(
                {"error": "Couldn't get number of events for organisation."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"events": events}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["POST"], url_path="update-subscription")
    @swagger_auto_schema(responses={200: OrganisationSerializerFull})
    def update_subscription(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            OrganisationSerializerFull(instance=self.get_object()).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["GET"],
        url_path="get-subscription-metadata",
    )
    def get_subscription_metadata(self, request, pk):
        organisation = self.get_object()
        if not organisation.has_subscription():
            raise SubscriptionNotFound()

        subscription_details = organisation.subscription.get_subscription_metadata()
        serializer = self.get_serializer(instance=subscription_details)

        return Response(serializer.data)

    @action(detail=True, methods=["GET"], url_path="portal-url")
    def get_portal_url(self, request, pk):
        organisation = self.get_object()
        if not organisation.has_subscription():
            raise OrganisationHasNoSubscription()
        redirect_url = get_current_site(request)
        serializer = self.get_serializer(
            data={"url": organisation.subscription.get_portal_url(redirect_url)}
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["POST"],
        url_path="get-hosted-page-url-for-subscription-upgrade",
    )
    def get_hosted_page_url_for_subscription_upgrade(self, request, pk):
        organisation = self.get_object()
        if not organisation.has_subscription():
            raise OrganisationHasNoSubscription()
        serializer = self.get_serializer(
            data={
                "subscription_id": organisation.subscription.subscription_id,
                **request.data,
            }
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @swagger_auto_schema(
        deprecated=True,
        operation_description="Please use ​​/api​/v1​/organisations​/{organisation_pk}​/usage-data​/",
        query_serializer=InfluxDataQuerySerializer(),
    )
    @action(detail=True, methods=["GET"], url_path="influx-data")
    def get_influx_data(self, request, pk):
        filters = InfluxDataQuerySerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        serializer = self.get_serializer(
            data={
                "events_list": get_multiple_event_list_for_organisation(
                    pk, **filters.data
                )
            }
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    @action(detail=False, methods=["GET"])
    def permissions(self, request):
        organisation_permissions = OrganisationPermissionModel.objects.all()
        serializer = self.get_serializer(instance=organisation_permissions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["GET"], url_path="my-permissions")
    def my_permissions(self, request, pk):
        org = self.get_object()

        permission_data = get_organisation_permission_data(
            org.id,
            user=request.user,
        )
        serializer = UserObjectPermissionsSerializer(instance=permission_data)

        return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([BasicAuthentication])
def chargebee_webhook(request):
    """
    Endpoint to handle webhooks from chargebee.

     - If subscription is active, check to see if plan has changed and update if so. Always update cancellation date to
       None to ensure that if a subscription is reactivated, it is updated on our end.

     - If subscription is cancelled or not renewing, update subscription on our end to include cancellation date and
       send alert to admin users.
    """

    if request.data.get("content") and "subscription" in request.data.get("content"):
        subscription_data: dict = request.data["content"]["subscription"]
        customer_email: str = request.data["content"]["customer"]["email"]

        try:
            existing_subscription = Subscription.objects.get(
                subscription_id=subscription_data.get("id")
            )
        except (Subscription.DoesNotExist, Subscription.MultipleObjectsReturned):
            error_message: str = (
                "Couldn't get unique subscription for ChargeBee id %s"
                % subscription_data.get("id")
            )
            logger.error(error_message)
            return Response(status=status.HTTP_200_OK)
        subscription_status = subscription_data.get("status")
        if subscription_status == "active":
            if subscription_data.get("plan_id") != existing_subscription.plan:
                existing_subscription.update_plan(subscription_data.get("plan_id"))
            subscription_metadata = extract_subscription_metadata(
                chargebee_subscription=subscription_data,
                customer_email=customer_email,
            )
            OrganisationSubscriptionInformationCache.objects.update_or_create(
                organisation_id=existing_subscription.organisation_id,
                defaults={
                    "chargebee_updated_at": timezone.now(),
                    "allowed_30d_api_calls": subscription_metadata.api_calls,
                    "allowed_seats": subscription_metadata.seats,
                    "organisation_id": existing_subscription.organisation_id,
                    "allowed_projects": subscription_metadata.projects,
                    "chargebee_email": subscription_metadata.chargebee_email,
                },
            )

        elif subscription_status in ("non_renewing", "cancelled"):
            existing_subscription.cancel(
                datetime.fromtimestamp(subscription_data.get("current_term_end")),
                update_chargebee=False,
            )

    return Response(status=status.HTTP_200_OK)


class OrganisationWebhookViewSet(viewsets.ModelViewSet, TriggerSampleWebhookMixin):
    serializer_class = OrganisationWebhookSerializer
    permission_classes = [IsAuthenticated, NestedOrganisationEntityPermission]

    webhook_type = WebhookType.ORGANISATION

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return OrganisationWebhook.objects.none()

        if "organisation_pk" not in self.kwargs:
            raise ValidationError("Missing required path parameter 'organisation_pk'")

        return OrganisationWebhook.objects.filter(
            organisation_id=self.kwargs["organisation_pk"]
        )

    def perform_update(self, serializer):
        organisation_id = self.kwargs["organisation_pk"]
        serializer.save(organisation_id=organisation_id)

    def perform_create(self, serializer):
        organisation_id = self.kwargs["organisation_pk"]
        serializer.save(organisation_id=organisation_id)
