"""QueryDict inputs retain their own nested data through validation and saving."""

from django.http import QueryDict
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from tests.models import Child, Parent
from tests.test_atomic_writes import ParentSerializer


def parent_querydict(name, children):
    data = QueryDict("", mutable=True)
    data["name"] = name
    data.setlist("child_set", children)
    return data


class LockedParentSerializer(ParentSerializer):
    def validate(self, attrs):
        # Consumer serializers inspect this raw payload during validation.
        if any(self._children_set.values()):
            raise ValidationError("Nested changes are locked.")
        return attrs


class TestNestedQueryDict(TransactionTestCase):
    def test_single_create_saves_all_children(self):
        serializer = ParentSerializer(
            data=parent_querydict("parent", [{"name": "first child"}, {"name": "second child"}])
        )
        serializer.is_valid(raise_exception=True)
        parent = serializer.save()

        self.assertEqual(
            list(parent.child_set.order_by("id").values_list("name", flat=True)),
            ["first child", "second child"],
        )

    def test_many_create_saves_each_inputs_children(self):
        serializer = ParentSerializer(
            data=[
                parent_querydict("first", [{"name": "first child"}]),
                parent_querydict("second", [{"name": "second child"}]),
            ],
            many=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        self.assertEqual(
            list(Child.objects.order_by("parent__name").values_list("parent__name", "name")),
            [("first", "first child"), ("second", "second child")],
        )

    def test_single_update_saves_its_children(self):
        parent = Parent.objects.create(name="parent")
        child = Child.objects.create(parent=parent, name="original child")
        serializer = ParentSerializer(
            parent,
            data=parent_querydict("changed parent", [{"id": child.id, "name": "changed child"}]),
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.name, "changed parent")
        self.assertEqual(child.name, "changed child")

    def test_single_validate_can_still_reject_raw_nested_changes(self):
        for data in (
            {"name": "parent", "child_set": [{"name": "child"}]},
            parent_querydict("parent", [{"name": "child"}]),
        ):
            with self.subTest(input_type=type(data).__name__):
                serializer = LockedParentSerializer(data=data)

                self.assertFalse(serializer.is_valid())
                self.assertEqual(serializer.errors["non_field_errors"], ["Nested changes are locked."])
