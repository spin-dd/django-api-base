"""A single serializer keeps its nested children out of validated_data."""

from django.http import QueryDict
from django.test import TransactionTestCase

from tests.models import Child, Parent
from tests.test_atomic_writes import ParentSerializer


def parent_querydict(name, children):
    data = QueryDict("", mutable=True)
    data["name"] = name
    data.setlist("child_set", children)
    return data


class ChildrenFirstParentSerializer(ParentSerializer):
    def update(self, instance, validated_data):
        # Consumers take the children to check them before the base update applies them.
        self.validated_children_set(validated_data)
        return super().update(instance, validated_data)


class TestSingleValidatedData(TransactionTestCase):
    def test_validated_data_has_only_model_fields(self):
        # Consumers pass validated_data to services and models, e.g. Parent(**validated_data).
        for data in (
            {"name": "parent", "child_set": [{"name": "child"}]},
            {"name": "parent"},
            parent_querydict("parent", [{"name": "child"}]),
        ):
            with self.subTest(data=data):
                serializer = ParentSerializer(data=data)
                serializer.is_valid(raise_exception=True)

                self.assertEqual(dict(serializer.validated_data), {"name": "parent"})

    def test_children_taken_before_update_are_still_saved(self):
        parent = Parent.objects.create(name="parent")
        child = Child.objects.create(parent=parent, name="original child")
        serializer = ChildrenFirstParentSerializer(
            parent,
            data={"name": "changed parent", "child_set": [{"id": child.id, "name": "changed child"}]},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        child.refresh_from_db()
        self.assertEqual(child.name, "changed child")
