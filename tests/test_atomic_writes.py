"""A failed nested write must leave no partial database changes."""

from django.db import IntegrityError
from django.test import TransactionTestCase, override_settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from apibase.serializers import BaseModelSerializer, BatchListSerializer, BatchSerializerMixin
from apibase.viewsets import BaseModelViewSet
from tests.models import Child, Parent


class ChildSerializer(BaseModelSerializer):
    # Let NULL reach the real NOT NULL constraint to exercise database failures.
    name = serializers.CharField(allow_null=True)

    class Meta:
        model = Child
        fields = ["id", "parent", "name"]


class ParentSerializer(BaseModelSerializer):
    child_set = ChildSerializer(many=True, required=False)
    nested_fields = ["child_set"]

    class Meta:
        model = Parent
        fields = ["id", "name", "child_set"]


class TestNestedCreate(TransactionTestCase):
    def test_child_validation_error_rolls_back_parent_and_earlier_child(self):
        serializer = ParentSerializer(
            data={"name": "new parent", "child_set": [{"name": "first child"}, {"name": ""}]}
        )
        serializer.is_valid(raise_exception=True)

        with self.assertRaises(ValidationError):
            serializer.save()

        self.assertEqual(list(Parent.objects.values_list("name", flat=True)), [])
        self.assertEqual(list(Child.objects.values_list("name", flat=True)), [])

    def test_child_database_error_rolls_back_parent_and_earlier_child(self):
        serializer = ParentSerializer(
            data={"name": "new parent", "child_set": [{"name": "first child"}, {"name": None}]}
        )
        serializer.is_valid(raise_exception=True)

        with self.assertRaises(IntegrityError):
            serializer.save()

        self.assertEqual(list(Parent.objects.values_list("name", flat=True)), [])
        self.assertEqual(list(Child.objects.values_list("name", flat=True)), [])

    def test_success_saves_parent_and_all_children(self):
        serializer = ParentSerializer(
            data={"name": "new parent", "child_set": [{"name": "first child"}, {"name": "second child"}]}
        )
        serializer.is_valid(raise_exception=True)
        parent = serializer.save()

        parent.refresh_from_db()
        self.assertEqual(parent.name, "new parent")
        self.assertEqual(
            list(parent.child_set.order_by("id").values_list("name", flat=True)), ["first child", "second child"]
        )


@override_settings(DATABASE_ROUTERS=["tests.routers.AtomicWritesRouter"])
class TestRoutedNestedCreate(TestNestedCreate):
    databases = {"default", "other"}


class TestNestedUpdate(TransactionTestCase):
    def setUp(self):
        self.parent = Parent.objects.create(name="original parent")
        self.child = Child.objects.create(parent=self.parent, name="original child")

    def test_child_validation_error_restores_parent_and_earlier_children(self):
        serializer = ParentSerializer(
            self.parent,
            data={
                "name": "changed parent",
                "child_set": [
                    {"id": self.child.id, "name": "changed child"},
                    {"name": "new child"},
                    {"name": ""},
                ],
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with self.assertRaises(ValidationError):
            serializer.save()

        self.parent.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(self.parent.name, "original parent")
        self.assertEqual(self.child.name, "original child")
        self.assertEqual(list(self.parent.child_set.values_list("id", flat=True)), [self.child.id])

    def test_child_database_error_restores_parent_and_earlier_children(self):
        serializer = ParentSerializer(
            self.parent,
            data={
                "name": "changed parent",
                "child_set": [
                    {"id": self.child.id, "name": "changed child"},
                    {"name": "new child"},
                    {"name": None},
                ],
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with self.assertRaises(IntegrityError):
            serializer.save()

        self.parent.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(self.parent.name, "original parent")
        self.assertEqual(self.child.name, "original child")
        self.assertEqual(list(self.parent.child_set.values_list("id", flat=True)), [self.child.id])

    def test_success_updates_parent_and_children(self):
        serializer = ParentSerializer(
            self.parent,
            data={
                "name": "changed parent",
                "child_set": [
                    {"id": self.child.id, "name": "changed child"},
                    {"name": "new child"},
                ],
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        self.parent.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(self.parent.name, "changed parent")
        self.assertEqual(self.child.name, "changed child")
        self.assertEqual(
            list(self.parent.child_set.order_by("id").values_list("name", flat=True)), ["changed child", "new child"]
        )


@override_settings(DATABASE_ROUTERS=["tests.routers.AtomicWritesRouter"])
class TestRoutedNestedUpdate(TestNestedUpdate):
    databases = {"default", "other"}


@override_settings(DATABASE_ROUTERS=["tests.routers.InstanceWritesRouter"])
class TestRoutedUpdateInstanceHint(TransactionTestCase):
    databases = {"default", "other"}

    def test_child_error_restores_parent_and_children_on_the_instance_database(self):
        parent = Parent.objects.using("other").create(name="original parent")
        first = Child.objects.using("other").create(parent=parent, name="original first")
        second = Child.objects.using("other").create(parent=parent, name="original second")
        serializer = ParentSerializer(
            parent,
            data={
                "name": "changed parent",
                "child_set": [
                    {"id": first.id, "name": "changed first"},
                    {"id": second.id, "name": None},
                ],
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        with self.assertRaises(IntegrityError):
            serializer.save()

        parent.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(parent.name, "original parent")
        self.assertEqual(first.name, "original first")
        self.assertEqual(second.name, "original second")


class PlainParentSerializer(BaseModelSerializer):
    name = serializers.CharField(allow_null=True)

    class Meta:
        model = Parent
        fields = ["id", "name"]


class BatchParentSerializer(BatchSerializerMixin, PlainParentSerializer):
    class Meta(PlainParentSerializer.Meta):
        list_serializer_class = BatchListSerializer


class ParentViewSet(BaseModelViewSet):
    queryset = Parent.objects.order_by("id")
    # Creation must also work with DRF's default ListSerializer.
    serializer_class = PlainParentSerializer


class BatchParentViewSet(ParentViewSet):
    serializer_class = BatchParentSerializer


class NestedParentViewSet(ParentViewSet):
    serializer_class = ParentSerializer


class NestedBatchParentSerializer(BatchSerializerMixin, ParentSerializer):
    class Meta(ParentSerializer.Meta):
        list_serializer_class = BatchListSerializer


class NestedBatchParentViewSet(ParentViewSet):
    serializer_class = NestedBatchParentSerializer


class TestBatchCreate(TransactionTestCase):
    def test_database_error_in_second_record_rolls_back_first_record(self):
        request = APIRequestFactory().post(
            "/parents/batch_create/", [{"name": "first"}, {"name": None}], format="json"
        )

        with self.assertRaises(IntegrityError):
            ParentViewSet.as_view({"post": "batch_create"})(request)

        self.assertEqual(list(Parent.objects.values_list("name", flat=True)), [])

    def test_success_saves_all_records(self):
        request = APIRequestFactory().post(
            "/parents/batch_create/", [{"name": "first"}, {"name": "second"}], format="json"
        )
        response = ParentViewSet.as_view({"post": "batch_create"})(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(list(Parent.objects.order_by("id").values_list("name", flat=True)), ["first", "second"])

    def test_each_parent_receives_its_own_nested_children(self):
        request = APIRequestFactory().post(
            "/parents/batch_create/",
            [
                {"name": "first", "child_set": [{"name": "first child"}]},
                {"name": "second", "child_set": [{"name": "second child"}]},
            ],
            format="json",
        )
        response = NestedParentViewSet.as_view({"post": "batch_create"})(request)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            list(Child.objects.order_by("parent__name").values_list("parent__name", "name")),
            [("first", "first child"), ("second", "second child")],
        )

    def test_missing_or_empty_children_stay_with_their_parent(self):
        for empty_children in (None, []):
            for empty_index in (0, 1):
                with self.subTest(empty_children=empty_children, empty_index=empty_index):
                    data = [
                        {"name": "first", "child_set": [{"name": "first child"}]},
                        {"name": "second", "child_set": [{"name": "second child"}]},
                    ]
                    if empty_children is None:
                        data[empty_index].pop("child_set")
                    else:
                        data[empty_index]["child_set"] = empty_children
                    request = APIRequestFactory().post("/parents/batch_create/", data, format="json")
                    response = NestedParentViewSet.as_view({"post": "batch_create"})(request)

                    self.assertEqual(response.status_code, 201)
                    expected = [["first child"], ["second child"]]
                    expected[empty_index] = []
                    self.assertEqual(
                        [[child["name"] for child in parent["child_set"]] for parent in response.data], expected
                    )

    def test_invalid_children_of_first_parent_roll_back_the_batch(self):
        request = APIRequestFactory().post(
            "/parents/batch_create/",
            [
                {"name": "first", "child_set": [{"name": ""}]},
                {"name": "second", "child_set": [{"name": "valid child"}]},
            ],
            format="json",
        )
        response = NestedParentViewSet.as_view({"post": "batch_create"})(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(Parent.objects.values_list("name", flat=True)), [])
        self.assertEqual(list(Child.objects.values_list("name", flat=True)), [])


@override_settings(DATABASE_ROUTERS=["tests.routers.AtomicWritesRouter"])
class TestRoutedBatchCreate(TestBatchCreate):
    databases = {"default", "other"}


class TestBatchUpdate(TransactionTestCase):
    def test_database_error_in_second_record_restores_first_record(self):
        first = Parent.objects.create(name="original first")
        second = Parent.objects.create(name="original second")
        request = APIRequestFactory().patch(
            "/parents/batch_update/",
            [{"id": first.id, "name": "changed first"}, {"id": second.id, "name": None}],
            format="json",
        )

        with self.assertRaises(IntegrityError):
            BatchParentViewSet.as_view({"patch": "batch_update"})(request)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "original first")
        self.assertEqual(second.name, "original second")

    def test_success_updates_all_records(self):
        first = Parent.objects.create(name="original first")
        second = Parent.objects.create(name="original second")
        request = APIRequestFactory().patch(
            "/parents/batch_update/",
            [{"id": first.id, "name": "changed first"}, {"id": second.id, "name": "changed second"}],
            format="json",
        )
        response = BatchParentViewSet.as_view({"patch": "batch_update"})(request)

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "changed first")
        self.assertEqual(second.name, "changed second")

    def test_each_parent_updates_its_own_nested_children(self):
        first = Parent.objects.create(name="first")
        second = Parent.objects.create(name="second")
        first_child = Child.objects.create(parent=first, name="original first child")
        second_child = Child.objects.create(parent=second, name="original second child")
        request = APIRequestFactory().patch(
            "/parents/batch_update/",
            [
                {"id": first.id, "child_set": [{"id": first_child.id, "name": "changed first child"}]},
                {"id": second.id, "child_set": [{"id": second_child.id, "name": "changed second child"}]},
            ],
            format="json",
        )
        response = NestedBatchParentViewSet.as_view({"patch": "batch_update"})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(Child.objects.order_by("parent__name").values_list("parent__name", "name")),
            [("first", "changed first child"), ("second", "changed second child")],
        )

    def test_missing_or_empty_children_do_not_replace_another_parents_update(self):
        for empty_children in (None, []):
            with self.subTest(empty_children=empty_children):
                first = Parent.objects.create(name="first")
                second = Parent.objects.create(name="second")
                first_child = Child.objects.create(parent=first, name="original first child")
                second_child = Child.objects.create(parent=second, name="original second child")
                data = [
                    {"id": first.id, "child_set": [{"id": first_child.id, "name": "changed first child"}]},
                    {"id": second.id},
                ]
                if empty_children is not None:
                    data[1]["child_set"] = empty_children
                request = APIRequestFactory().patch("/parents/batch_update/", data, format="json")
                response = NestedBatchParentViewSet.as_view({"patch": "batch_update"})(request)

                self.assertEqual(response.status_code, 200)
                first_child.refresh_from_db()
                second_child.refresh_from_db()
                self.assertEqual(first_child.name, "changed first child")
                self.assertEqual(second_child.name, "original second child")
                self.assertEqual(first_child.parent_id, first.id)
                self.assertEqual(second_child.parent_id, second.id)

    def test_invalid_children_of_first_parent_restore_the_batch(self):
        first = Parent.objects.create(name="first")
        second = Parent.objects.create(name="second")
        first_child = Child.objects.create(parent=first, name="original first child")
        second_child = Child.objects.create(parent=second, name="original second child")
        request = APIRequestFactory().patch(
            "/parents/batch_update/",
            [
                {"id": first.id, "name": "changed first", "child_set": [{"id": first_child.id, "name": ""}]},
                {"id": second.id, "child_set": [{"id": second_child.id, "name": "changed second child"}]},
            ],
            format="json",
        )
        response = NestedBatchParentViewSet.as_view({"patch": "batch_update"})(request)

        self.assertEqual(response.status_code, 400)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "first")
        self.assertEqual(second.name, "second")
        self.assertEqual(
            list(Child.objects.order_by("parent__name").values_list("parent__name", "name")),
            [("first", "original first child"), ("second", "original second child")],
        )


@override_settings(DATABASE_ROUTERS=["tests.routers.AtomicWritesRouter"])
class TestRoutedBatchUpdate(TestBatchUpdate):
    databases = {"default", "other"}
