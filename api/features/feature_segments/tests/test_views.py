import json

import pytest
from django.urls import reverse
from pytest_lazyfixture import lazy_fixture
from rest_framework import status

from environments.models import Environment
from features.models import Feature, FeatureSegment
from segments.models import Segment


@pytest.mark.parametrize(
    "client, num_queries",
    [
        (lazy_fixture("admin_client"), 2),  # 1 for paging, 1 for result
        (
            lazy_fixture("admin_master_api_key_client"),
            3,
        ),  # an extra one for master_api_key
    ],
)
def test_list_feature_segments(
    segment,
    feature,
    environment,
    project,
    django_assert_num_queries,
    client,
    feature_segment,
    num_queries,
):
    # Given
    base_url = reverse("api-v1:features:feature-segment-list")
    url = f"{base_url}?environment={environment.id}&feature={feature.id}"
    environment_2 = Environment.objects.create(
        project=project, name="Test environment 2"
    )
    segment_2 = Segment.objects.create(project=project, name="Segment 2")
    segment_3 = Segment.objects.create(project=project, name="Segment 3")

    FeatureSegment.objects.create(
        feature=feature, segment=segment_2, environment=environment
    )
    FeatureSegment.objects.create(
        feature=feature, segment=segment_3, environment=environment
    )
    FeatureSegment.objects.create(
        feature=feature, segment=segment, environment=environment_2
    )

    # When
    with django_assert_num_queries(num_queries):
        response = client.get(url)

    # Then
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json["count"] == 3
    for result in response_json["results"]:
        assert result["environment"] == environment.id
        assert "uuid" in result
        assert "segment_name" in result
        assert not result["is_feature_specific"]


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_client"), lazy_fixture("admin_master_api_key_client")],
)
def test_list_feature_segments_is_feature_specific(
    segment,
    feature,
    environment,
    project,
    client,
):
    # Given
    base_url = reverse("api-v1:features:feature-segment-list")
    url = f"{base_url}?environment={environment.id}&feature={feature.id}"

    segment = Segment.objects.create(
        project=project, name="Test segment", feature=feature
    )
    FeatureSegment.objects.create(
        feature=feature, segment=segment, environment=environment
    )

    # When
    response = client.get(url)

    # Then
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json["count"] == 1
    assert response_json["results"][0]["is_feature_specific"]


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_create_feature_segment(segment, feature, environment, client):
    # Given
    data = {
        "feature": feature.id,
        "segment": segment.id,
        "environment": environment.id,
    }
    url = reverse("api-v1:features:feature-segment-list")

    # When
    response = client.post(url, data=json.dumps(data), content_type="application/json")

    # Then
    assert response.status_code == status.HTTP_201_CREATED
    response_json = response.json()
    assert response_json["id"]


def test_create_feature_segment_without_permission_returns_403(
    segment, feature, environment, test_user_client
):
    # Given
    data = {
        "feature": feature.id,
        "segment": segment.id,
        "environment": environment.id,
    }
    url = reverse("api-v1:features:feature-segment-list")

    # When
    response = test_user_client.post(
        url, data=json.dumps(data), content_type="application/json"
    )

    # Then
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_delete_feature_segment(segment, feature, environment, client):
    # Given
    feature_segment = FeatureSegment.objects.create(
        feature=feature, environment=environment, segment=segment
    )
    url = reverse("api-v1:features:feature-segment-detail", args=[feature_segment.id])

    # When
    response = client.delete(url)

    # Then
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not FeatureSegment.objects.filter(id=feature_segment.id).exists()


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_update_priority_of_multiple_feature_segments(
    feature_segment,
    project,
    client,
    environment,
    feature,
    admin_user,
    master_api_key,
):
    # Given
    url = reverse("api-v1:features:feature-segment-update-priorities")

    # another segment and feature segments for the same feature
    another_segment = Segment.objects.create(name="Another segment", project=project)
    another_feature_segment = FeatureSegment.objects.create(
        segment=another_segment, environment=environment, feature=feature
    )

    # reorder the feature segments
    assert feature_segment.priority == 0
    assert another_feature_segment.priority == 1
    data = [
        {"id": feature_segment.id, "priority": 1},
        {"id": another_feature_segment.id, "priority": 0},
    ]

    # When
    response = client.post(url, data=json.dumps(data), content_type="application/json")

    # Then the segments are reordered
    assert response.status_code == status.HTTP_200_OK
    json_response = response.json()
    assert json_response[0]["id"] == feature_segment.id
    assert json_response[1]["id"] == another_feature_segment.id


def test_update_priority_returns_403_if_user_does_not_have_permission(
    feature_segment,
    project,
    environment,
    feature,
    test_user_client,
):
    # Given
    url = reverse("api-v1:features:feature-segment-update-priorities")

    data = [
        {"id": feature_segment.id, "priority": 1},
    ]

    # When
    response = test_user_client.post(
        url, data=json.dumps(data), content_type="application/json"
    )

    # Then
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_update_priorities_empty_list(client):
    # Given
    url = reverse("api-v1:features:feature-segment-update-priorities")

    # When
    response = client.post(url, data=json.dumps([]), content_type="application/json")

    # Then the segments are reordered
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_get_feature_segment_by_uuid(
    feature_segment, project, client, environment, feature
):
    # Given
    url = reverse(
        "api-v1:features:feature-segment-get-by-uuid", args=[feature_segment.uuid]
    )

    # When
    response = client.get(url)

    # Then
    assert response.status_code == status.HTTP_200_OK
    json_response = response.json()
    assert json_response["id"] == feature_segment.id
    assert json_response["uuid"] == str(feature_segment.uuid)


def test_get_feature_segment_by_uuid_returns_404_if_user_does_not_have_access(
    feature_segment, project, test_user_client, environment, feature
):
    # Given
    url = reverse(
        "api-v1:features:feature-segment-get-by-uuid", args=[feature_segment.uuid]
    )

    # When
    response = test_user_client.get(url)

    # Then
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_get_feature_segment_by_id(
    feature_segment, project, client, environment, feature
):
    # Given
    url = reverse("api-v1:features:feature-segment-detail", args=[feature_segment.id])

    # When
    response = client.get(url)

    # Then
    assert response.status_code == status.HTTP_200_OK
    json_response = response.json()
    assert json_response["id"] == feature_segment.id
    assert json_response["uuid"] == str(feature_segment.uuid)


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_creating_segment_override_for_feature_based_segment_returns_400_for_wrong_feature(
    client, feature_based_segment, project, environment
):
    # Given - A different feature
    feature = Feature.objects.create(name="Feature 2", project=project)
    data = {
        "feature": feature.id,
        "segment": feature_based_segment.id,
        "environment": environment.id,
    }
    url = reverse("api-v1:features:feature-segment-list")

    # When
    response = client.post(url, data=json.dumps(data), content_type="application/json")

    # Then
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        response.json()["feature"][0]
        == "Can only create segment override(using this segment) for feature %d"
        % feature_based_segment.feature.id
    )


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_creating_segment_override_for_feature_based_segment_returns_201_for_correct_feature(
    client, feature_based_segment, project, environment, feature
):
    # Given
    data = {
        "feature": feature.id,
        "segment": feature_based_segment.id,
        "environment": environment.id,
    }
    url = reverse("api-v1:features:feature-segment-list")

    # When
    response = client.post(url, data=json.dumps(data), content_type="application/json")
    # Then
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.parametrize(
    "client",
    [lazy_fixture("admin_master_api_key_client"), lazy_fixture("admin_client")],
)
def test_creating_segment_override_reaching_max_limit(
    client, segment, environment, project, feature, feature_based_segment
):
    # Given
    project.max_segment_overrides_allowed = 1
    project.save()

    data = {
        "feature": feature.id,
        "segment": segment.id,
        "environment": environment.id,
    }
    url = reverse("api-v1:features:feature-segment-list")
    # let's create the first segment override
    response = client.post(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == status.HTTP_201_CREATED

    # Then - Try to create another override
    data = {
        "feature": feature.id,
        "segment": feature_based_segment.id,
        "environment": environment.id,
    }
    response = client.post(url, data=json.dumps(data), content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        response.json()["environment"][0]
        == "The environment has reached the maximum allowed segments overrides limit."
    )
    assert environment.feature_segments.count() == 1
