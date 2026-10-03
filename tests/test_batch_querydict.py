"""Form batch updates match string lookup ids to real database records."""

from django.http import QueryDict
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory

from tests.models import Parent
from tests.test_atomic_writes import BatchParentViewSet


class TestBatchQueryDict(TransactionTestCase):
    def test_form_batch_update_updates_all_records(self):
        first = Parent.objects.create(name="original first")
        second = Parent.objects.create(name="original second")
        untouched = Parent.objects.create(name="untouched")
        data = QueryDict("", mutable=True)
        data.update(
            {
                "[0]id": str(second.id),
                "[0]name": "changed second",
                "[1]id": str(first.id),
                "[1]name": "changed first",
            }
        )
        request = APIRequestFactory().patch(
            "/parents/batch_update/", data.urlencode(), content_type="application/x-www-form-urlencoded"
        )
        response = BatchParentViewSet.as_view({"patch": "batch_update"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(parent["id"], parent["name"]) for parent in response.data],
            [(first.id, "changed first"), (second.id, "changed second")],
        )
        first.refresh_from_db()
        second.refresh_from_db()
        untouched.refresh_from_db()
        self.assertEqual(first.name, "changed first")
        self.assertEqual(second.name, "changed second")
        self.assertEqual(untouched.name, "untouched")

    def assert_batch_without_id_rejected(self, method, form):
        first = Parent.objects.create(name="original first")
        second = Parent.objects.create(name="original second")
        factory_method = getattr(APIRequestFactory(), method)
        if form:
            data = QueryDict("", mutable=True)
            data.update({"[0]id": str(first.id), "[0]name": "changed first", "[1]name": "changed second"})
            request = factory_method(
                "/parents/batch_update/", data.urlencode(), content_type="application/x-www-form-urlencoded"
            )
        else:
            request = factory_method(
                "/parents/batch_update/",
                [{"id": first.id, "name": "changed first"}, {"name": "changed second"}],
                format="json",
            )
        response = BatchParentViewSet.as_view({method: "batch_update"})(request)

        self.assertEqual(response.status_code, 400)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "original first")
        self.assertEqual(second.name, "original second")

    def test_form_batch_patch_without_id_returns_400(self):
        self.assert_batch_without_id_rejected("patch", form=True)

    def test_form_batch_put_without_id_returns_400(self):
        self.assert_batch_without_id_rejected("put", form=True)

    def test_json_batch_patch_without_id_returns_400(self):
        self.assert_batch_without_id_rejected("patch", form=False)

    def test_json_batch_put_without_id_returns_400(self):
        self.assert_batch_without_id_rejected("put", form=False)
