"""Single updates keep the instance selected by the URL."""

from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory

from tests.models import Parent
from tests.test_atomic_writes import ParentViewSet


class TestSingleUpdate(TransactionTestCase):
    def test_patch_ignores_body_id(self) -> None:
        first = Parent.objects.create(name="original first")
        second = Parent.objects.create(name="original second")
        request = APIRequestFactory().patch(
            f"/parents/{first.id}/", {"id": second.id, "name": "changed first"}, format="json"
        )
        response = ParentViewSet.as_view({"patch": "partial_update"})(request, pk=str(first.id))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "changed first")
        self.assertEqual(second.name, "original second")
        self.assertEqual(response.data["id"], first.id)
