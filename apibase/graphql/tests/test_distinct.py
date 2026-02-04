"""
Tests for conditional distinct() in NodeSet.resolve_queryset().

TDD: These tests are written BEFORE implementation.
The helper functions being tested:
- _filter_needs_distinct(filter_field, model)
- _queryset_has_duplicating_joins(qs)
- _needs_distinct(qs, args, filterset_class)
"""

from unittest.mock import MagicMock, PropertyMock

import pytest


def create_mock_filter(field_name, distinct=False, method=None):
    """Create a mock filter field."""
    filter_field = MagicMock()
    filter_field.field_name = field_name
    filter_field.distinct = distinct
    filter_field.method = method
    return filter_field


def create_mock_field(many_to_many=False, one_to_many=False):
    """Create a mock Django field."""
    field = MagicMock()
    field.many_to_many = many_to_many
    field.one_to_many = one_to_many
    return field


def create_mock_filterset_class(base_filters, model=None):
    """Create a mock FilterSet class."""
    filterset_class = MagicMock()
    filterset_class.base_filters = base_filters
    filterset_class._meta = MagicMock()
    filterset_class._meta.model = model
    return filterset_class


class TestFilterNeedsDistinct:
    """Tests for _filter_needs_distinct() helper function."""

    def test_explicit_distinct_true_returns_true(self):
        """Filter with distinct=True should return True."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("title", distinct=True)
        model = MagicMock()

        result = _filter_needs_distinct(filter_field, model)
        assert result is True

    def test_simple_field_returns_false(self):
        """Simple field filter should return False."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("is_active", distinct=False)
        model = MagicMock()

        # Mock get_field_parts to return a simple field
        simple_field = create_mock_field(many_to_many=False, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "apibase.graphql.fields.get_field_parts", lambda m, f: [simple_field] if f == "is_active" else []
            )
            result = _filter_needs_distinct(filter_field, model)

        assert result is False

    def test_fk_field_returns_false(self):
        """FK field filter should return False."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("author_id", distinct=False)
        model = MagicMock()

        # FK field - not many_to_many, not one_to_many
        fk_field = create_mock_field(many_to_many=False, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [fk_field])
            result = _filter_needs_distinct(filter_field, model)

        assert result is False

    def test_m2m_field_returns_true(self):
        """M2M field filter should return True."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("tags__name", distinct=False)
        model = MagicMock()

        # M2M field
        m2m_field = create_mock_field(many_to_many=True, one_to_many=False)
        name_field = create_mock_field(many_to_many=False, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [m2m_field, name_field])
            result = _filter_needs_distinct(filter_field, model)

        assert result is True

    def test_reverse_fk_field_returns_true(self):
        """Reverse FK field filter (one_to_many) should return True."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("comments__text", distinct=False)
        model = MagicMock()

        # Reverse FK field (one_to_many)
        reverse_fk_field = create_mock_field(many_to_many=False, one_to_many=True)
        text_field = create_mock_field(many_to_many=False, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [reverse_fk_field, text_field])
            result = _filter_needs_distinct(filter_field, model)

        assert result is True

    def test_method_filter_without_distinct_returns_false(self):
        """Method filter without distinct=True should return False."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("custom", distinct=False, method="filter_custom")
        model = MagicMock()

        # Method filters don't have valid field_name for get_field_parts
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [])
            result = _filter_needs_distinct(filter_field, model)

        assert result is False

    def test_method_filter_with_distinct_returns_true(self):
        """Method filter with distinct=True should return True."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("custom", distinct=True, method="filter_custom")
        model = MagicMock()

        # Distinct=True takes precedence, no need to check field parts
        result = _filter_needs_distinct(filter_field, model)
        assert result is True

    def test_get_field_parts_exception_returns_false(self):
        """When get_field_parts raises, should return False (continue to next layer)."""
        from apibase.graphql.fields import _filter_needs_distinct

        filter_field = create_mock_filter("invalid_field", distinct=False)
        model = MagicMock()

        with pytest.MonkeyPatch.context() as mp:

            def raise_error(m, f):
                raise Exception("Field not found")

            mp.setattr("apibase.graphql.fields.get_field_parts", raise_error)
            result = _filter_needs_distinct(filter_field, model)

        assert result is False


class TestQuerysetHasDuplicatingJoins:
    """Tests for _queryset_has_duplicating_joins() fallback function."""

    def test_empty_alias_map_returns_false(self):
        """QuerySet with no joins should return False."""
        from apibase.graphql.fields import _queryset_has_duplicating_joins

        qs = MagicMock()
        qs.query.alias_map = {}

        result = _queryset_has_duplicating_joins(qs)
        assert result is False

    def test_m2m_join_returns_true(self):
        """QuerySet with M2M join should return True."""
        from django.db.models.sql.datastructures import Join

        from apibase.graphql.fields import _queryset_has_duplicating_joins

        # Create a proper Join-like object using the actual Join class signature
        # We need to create a mock that passes isinstance(obj, Join)
        join_field = create_mock_field(many_to_many=True, one_to_many=False)

        # Create an actual Join instance (or close enough for isinstance check)
        # The function checks isinstance(join_info, Join), so we use a real Join
        # But we need to mock the join_field attribute
        class MockJoin(Join):
            """Mock Join that overrides join_field."""

            def __init__(self, join_field):
                self._join_field = join_field

            @property
            def join_field(self):
                return self._join_field

        mock_join = MockJoin(join_field)

        qs = MagicMock()
        qs.query.alias_map = {"tags": mock_join}

        result = _queryset_has_duplicating_joins(qs)
        assert result is True

    def test_exception_returns_true(self):
        """On error, should conservatively return True."""
        from apibase.graphql.fields import _queryset_has_duplicating_joins

        qs = MagicMock()
        type(qs.query).alias_map = PropertyMock(side_effect=Exception("test error"))

        result = _queryset_has_duplicating_joins(qs)
        assert result is True


class TestNeedsDistinct:
    """Tests for _needs_distinct() composite function."""

    def test_no_filterset_class_returns_false(self):
        """When filterset_class is None, return False."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        result = _needs_distinct(qs, args={"is_active": True}, filterset_class=None)
        assert result is False

    def test_no_filters_applied_returns_false(self):
        """When no filters are applied (empty args), return False."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        filterset_class = create_mock_filterset_class(
            base_filters={"is_active": create_mock_filter("is_active")}, model=MagicMock()
        )

        result = _needs_distinct(qs, args={}, filterset_class=filterset_class)
        assert result is False

    def test_filter_arg_not_in_base_filters_returns_false(self):
        """When filter arg doesn't match any base_filter, return False."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        qs.query.alias_map = {}
        filterset_class = create_mock_filterset_class(
            base_filters={"is_active": create_mock_filter("is_active")}, model=MagicMock()
        )

        # 'unknown' is not in base_filters
        result = _needs_distinct(qs, args={"unknown": True}, filterset_class=filterset_class)
        assert result is False

    def test_simple_filter_returns_false(self):
        """Simple filter (is_active) should return False."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        qs.query.alias_map = {}

        simple_filter = create_mock_filter("is_active", distinct=False)
        filterset_class = create_mock_filterset_class(base_filters={"is_active": simple_filter}, model=MagicMock())

        # Mock get_field_parts to return simple field
        simple_field = create_mock_field(many_to_many=False, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [simple_field])
            result = _needs_distinct(qs, args={"is_active": True}, filterset_class=filterset_class)

        assert result is False

    def test_m2m_filter_returns_true(self):
        """M2M filter should return True."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        qs.query.alias_map = {}

        m2m_filter = create_mock_filter("tags__name", distinct=False)
        filterset_class = create_mock_filterset_class(base_filters={"tags__name": m2m_filter}, model=MagicMock())

        # Mock get_field_parts to return M2M field
        m2m_field = create_mock_field(many_to_many=True, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [m2m_field])
            result = _needs_distinct(qs, args={"tags__name": "python"}, filterset_class=filterset_class)

        assert result is True

    def test_multiple_filters_one_needs_distinct_returns_true(self):
        """If any filter needs distinct, return True."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        qs.query.alias_map = {}

        simple_filter = create_mock_filter("is_active", distinct=False)
        m2m_filter = create_mock_filter("tags__name", distinct=False)
        filterset_class = create_mock_filterset_class(
            base_filters={"is_active": simple_filter, "tags__name": m2m_filter}, model=MagicMock()
        )

        # Mock get_field_parts
        simple_field = create_mock_field(many_to_many=False, one_to_many=False)
        m2m_field = create_mock_field(many_to_many=True, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:

            def get_parts(m, f):
                if f == "is_active":
                    return [simple_field]
                elif f == "tags__name":
                    return [m2m_field]
                return []

            mp.setattr("apibase.graphql.fields.get_field_parts", get_parts)
            result = _needs_distinct(
                qs, args={"is_active": True, "tags__name": "python"}, filterset_class=filterset_class
            )

        assert result is True

    def test_explicit_distinct_filter_returns_true(self):
        """Filter with explicit distinct=True should return True."""
        from apibase.graphql.fields import _needs_distinct

        qs = MagicMock()
        qs.query.alias_map = {}

        explicit_filter = create_mock_filter("title", distinct=True)
        filterset_class = create_mock_filterset_class(base_filters={"title": explicit_filter}, model=MagicMock())

        result = _needs_distinct(qs, args={"title": "test"}, filterset_class=filterset_class)
        assert result is True

    def test_fallback_to_queryset_joins(self):
        """When no filter needs distinct but QuerySet has M2M join, return True."""
        from django.db.models.sql.datastructures import Join

        from apibase.graphql.fields import _needs_distinct

        # Create a proper Join-like object
        join_field = create_mock_field(many_to_many=True, one_to_many=False)

        class MockJoin(Join):
            """Mock Join that overrides join_field."""

            def __init__(self, join_field):
                self._join_field = join_field

            @property
            def join_field(self):
                return self._join_field

        mock_join = MockJoin(join_field)

        qs = MagicMock()
        qs.query.alias_map = {"tags": mock_join}

        # Filter doesn't need distinct by itself
        simple_filter = create_mock_filter("is_active", distinct=False)
        filterset_class = create_mock_filterset_class(base_filters={"is_active": simple_filter}, model=MagicMock())

        simple_field = create_mock_field(many_to_many=False, one_to_many=False)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("apibase.graphql.fields.get_field_parts", lambda m, f: [simple_field])
            result = _needs_distinct(qs, args={"is_active": True}, filterset_class=filterset_class)

        assert result is True
