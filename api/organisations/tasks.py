from organisations import subscription_info_cache
from organisations.models import Organisation
from organisations.subscriptions.subscription_service import (
    get_subscription_metadata,
)
from task_processor.decorators import register_task_handler
from users.models import FFAdminUser

from .subscriptions.constants import SubscriptionCacheEntity

ALERT_EMAIL_MESSAGE = (
    "Organisation %s has used %d seats which is over their plan limit of %d (plan: %s)"
)
ALERT_EMAIL_SUBJECT = "Organisation over number of seats"


@register_task_handler()
def send_org_over_limit_alert(organisation_id):
    organisation = Organisation.objects.get(id=organisation_id)

    subscription_metadata = get_subscription_metadata(organisation)
    FFAdminUser.send_alert_to_admin_users(
        subject=ALERT_EMAIL_SUBJECT,
        message=ALERT_EMAIL_MESSAGE
        % (
            str(organisation.name),
            organisation.num_seats,
            subscription_metadata.seats,
            organisation.subscription.plan,
        ),
    )


@register_task_handler()
def update_organisation_subscription_information_influx_cache():
    subscription_info_cache.update_caches((SubscriptionCacheEntity.INFLUX,))


@register_task_handler()
def update_organisation_subscription_information_cache():
    subscription_info_cache.update_caches(
        (SubscriptionCacheEntity.CHARGEBEE, SubscriptionCacheEntity.INFLUX)
    )
