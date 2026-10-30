import pytest
from django.test import override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apibase.paginations import Pagination


@pytest.mark.parametrize(
    ("count", "page", "expected_page_range"),
    [
        (590000, 1, [1, 2, 3, 4, 5, 6]),
        (590000, 295000, list(range(294995, 295006))),
        (590000, 590000, list(range(589995, 590001))),
        (0, 1, [1]),
    ],
)
def test_page_range_lists_five_pages_around_current(count: int, page: int, expected_page_range: list[int]) -> None:
    request = Request(APIRequestFactory().get("/", {"page": page, "page_size": 1}))
    pagination = Pagination()
    data = pagination.paginate_queryset(range(count), request)

    with override_settings(ALLOWED_HOSTS=["testserver"]):
        response = pagination.get_paginated_response(data)

    assert list(response.data) == ["count", "page_range", "current_page", "next", "previous", "results"]
    assert response.data["page_range"] == expected_page_range
