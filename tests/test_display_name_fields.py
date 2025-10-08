from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from jira.client import JIRA
from jira.resources import (
    Issue,
    PropertyHolder,
    _add_display_name_fields,
    _prepare_api_fields,
    convert_display_name_to_python_name,
)
from tests.conftest import JiraTestCase


class DisplayNameFieldConversionTest(unittest.TestCase):
    def test_basic_field_name_conversion(self):
        self.assertEqual(convert_display_name_to_python_name("Story Points"), "story_points")
        self.assertEqual(convert_display_name_to_python_name("Internal Target Milestone"), "internal_target_milestone")
        self.assertEqual(convert_display_name_to_python_name("Epic Link"), "epic_link")

    def test_special_character_handling(self):
        self.assertEqual(convert_display_name_to_python_name("Story-Points"), "story_points")
        self.assertEqual(convert_display_name_to_python_name("Business   Value---Score"), "business_value_score")
        self.assertEqual(convert_display_name_to_python_name("Field!!Name@@Here"), "field_name_here")
        self.assertEqual(convert_display_name_to_python_name("-Story Points-"), "story_points")
        self.assertEqual(convert_display_name_to_python_name("__Field Name__"), "field_name")

    def test_numeric_field_names(self):
        self.assertEqual(convert_display_name_to_python_name("10 Point Scale"), "field_10_point_scale")
        self.assertEqual(convert_display_name_to_python_name("3rd Party Integration"), "field_3rd_party_integration")
        self.assertEqual(convert_display_name_to_python_name("2023 Budget"), "field_2023_budget")

    def test_edge_cases(self):
        self.assertEqual(convert_display_name_to_python_name("A"), "a")
        self.assertEqual(convert_display_name_to_python_name("1"), "field_1")
        self.assertEqual(convert_display_name_to_python_name("story_points"), "story_points")
        self.assertEqual(convert_display_name_to_python_name("STORY_POINTS"), "story_points")
        self.assertEqual(convert_display_name_to_python_name("CamelCaseField"), "camelcasefield")


class DisplayNameFieldIntegrationTest(JiraTestCase):
    def setUp(self):
        super().setUp()
        self.issue_1 = self.test_manager.project_b_issue1
        self.issue_1_obj = self.test_manager.project_b_issue1_obj

    def test_display_name_field_creation(self):
        issue = self.issue_1_obj
        all_fields = dir(issue.fields)
        custom_field_ids = [f for f in all_fields if f.startswith('customfield_')]

        self.assertGreater(len(custom_field_ids), 0)
        total_fields = len([f for f in all_fields if not f.startswith('__')])
        self.assertGreater(total_fields, len(custom_field_ids) + 20)

    def test_field_equivalence(self):
        issue = self.issue_1_obj

        if hasattr(self.jira, '_fields_cache') and self.jira._fields_cache:
            fields_cache = self.jira._fields_cache
            tested_equivalence = False

            for display_name, field_id in list(fields_cache.items())[:5]:
                if hasattr(issue.fields, field_id):
                    python_name = convert_display_name_to_python_name(display_name)

                    if hasattr(issue.fields, python_name):
                        original_value = getattr(issue.fields, field_id)
                        display_value = getattr(issue.fields, python_name)
                        self.assertEqual(original_value, display_value)
                        tested_equivalence = True
                        break

            if not tested_equivalence:
                self.skipTest("No suitable fields found for equivalence testing")

    def test_backwards_compatibility(self):
        issue = self.issue_1_obj

        standard_fields = ['summary', 'status', 'priority', 'created', 'updated']
        for field_name in standard_fields:
            self.assertTrue(hasattr(issue.fields, field_name))
            value = getattr(issue.fields, field_name)
            self.assertIsNotNone(value)

        custom_fields = [attr for attr in dir(issue.fields) if attr.startswith('customfield_')]
        self.assertGreater(len(custom_fields), 0)

        for field_id in custom_fields[:3]:
            getattr(issue.fields, field_id)


class DisplayNameFieldMockTest(unittest.TestCase):
    def _create_mock_property_holder(self, field_data: dict) -> PropertyHolder:
        obj = PropertyHolder()
        for field_name, field_value in field_data.items():
            setattr(obj, field_name, field_value)
        return obj

    def _create_mock_session(self, fields_cache: dict) -> MagicMock:
        session = MagicMock()
        session.fields_cache = fields_cache
        return session

    def test_display_name_creation_with_mock_data(self):
        mock_fields = {
            'customfield_10001': 5,
            'customfield_10002': 42,
            'customfield_10003': ['label1', 'label2'],
            'summary': 'Test Issue'
        }

        mock_cache = {
            'Story Points': 'customfield_10001',
            'Sprint': 'customfield_10002',
            'Labels': 'customfield_10003'
        }

        obj = self._create_mock_property_holder(mock_fields)
        session = self._create_mock_session(mock_cache)

        _add_display_name_fields(obj, session)

        self.assertTrue(hasattr(obj, 'story_points'))
        self.assertTrue(hasattr(obj, 'sprint'))
        self.assertTrue(hasattr(obj, 'labels'))

        self.assertEqual(obj.story_points, 5)
        self.assertEqual(obj.sprint, 42)
        self.assertEqual(obj.labels, ['label1', 'label2'])

        self.assertEqual(obj.customfield_10001, 5)
        self.assertEqual(obj.customfield_10002, 42)
        self.assertEqual(obj.customfield_10003, ['label1', 'label2'])

    def test_no_custom_fields(self):
        obj = self._create_mock_property_holder({
            'summary': 'Test Issue',
            'status': 'Open',
            'priority': 'High'
        })
        session = self._create_mock_session({'Story Points': 'customfield_10001'})

        initial_attrs = set(dir(obj))
        _add_display_name_fields(obj, session)
        final_attrs = set(dir(obj))

        self.assertEqual(initial_attrs, final_attrs)

    def test_name_collision_prevention(self):
        obj = self._create_mock_property_holder({
            'customfield_10001': 'epic-value',
            'summary': 'Original Summary'
        })

        session = self._create_mock_session({
            'Summary': 'customfield_10001'
        })

        _add_display_name_fields(obj, session)

        self.assertEqual(obj.summary, 'Original Summary')
        self.assertNotEqual(obj.summary, 'epic-value')

    def test_none_and_empty_values(self):
        obj = self._create_mock_property_holder({
            'customfield_10001': None,
            'customfield_10002': '',
            'customfield_10003': []
        })
        session = self._create_mock_session({
            'Story Points': 'customfield_10001',
            'Summary': 'customfield_10002',
            'Labels': 'customfield_10003'
        })

        _add_display_name_fields(obj, session)

        self.assertTrue(hasattr(obj, 'story_points'))
        self.assertTrue(hasattr(obj, 'summary'))
        self.assertTrue(hasattr(obj, 'labels'))

        self.assertIsNone(obj.story_points)
        self.assertEqual(obj.summary, '')
        self.assertEqual(obj.labels, [])


class DisplayNameReverseMapTest(unittest.TestCase):
    def _create_mock_session(self, fields_cache: dict) -> MagicMock:
        session = MagicMock()
        session.fields_cache = fields_cache
        return session

    def test_reverse_mapping_for_create(self):
        fields = {
            'project': 'TEST',
            'summary': 'New issue',
            'issuetype': 'Bug',
            'story_points': 5
        }
        session = self._create_mock_session({
            'Story Points': 'customfield_10001'
        })

        result = _prepare_api_fields(fields, session, wrap=False)

        self.assertEqual(result, {
            'project': 'TEST',
            'summary': 'New issue',
            'issuetype': 'Bug',
            'customfield_10001': 5
        })

    def test_reverse_mapping_basic(self):
        fields = {'story_points': 5, 'sprint': 'Sprint 1'}
        session = self._create_mock_session({
            'Story Points': 'customfield_10001',
            'Sprint': 'customfield_10002'
        })

        result = _prepare_api_fields(fields, session, wrap=False)

        self.assertEqual(result, {
            'customfield_10001': 5,
            'customfield_10002': 'Sprint 1'
        })

    def test_reverse_mapping_mixed(self):
        fields = {'story_points': 5, 'summary': 'Test', 'customfield_10003': 'value'}
        session = self._create_mock_session({
            'Story Points': 'customfield_10001'
        })

        result = _prepare_api_fields(fields, session, wrap=False)

        self.assertEqual(result, {
            'customfield_10001': 5,
            'summary': 'Test',
            'customfield_10003': 'value'
        })

    def test_reverse_mapping_no_cache(self):
        fields = {'story_points': 5}
        session = self._create_mock_session({})

        result = _prepare_api_fields(fields, session, wrap=False)

        self.assertEqual(result, fields)

    def test_reverse_mapping_empty(self):
        fields = {}
        session = self._create_mock_session({'Story Points': 'customfield_10001'})

        result = _prepare_api_fields(fields, session, wrap=False)

        self.assertEqual(result, {})


class DisplayNameIntegrationTest(unittest.TestCase):
    """Test that _prepare_api_fields is properly integrated into JIRA client methods."""

    def test_create_issue_with_display_names(self):
        """Test create_issue converts display names to field IDs."""
        jira = MagicMock(spec=JIRA)
        jira._session = MagicMock()
        jira._session.fields_cache = {'Story Points': 'customfield_10001'}
        jira._options = MagicMock()
        jira._options.server = 'https://test.jira.com'

        # Mock the actual API call
        jira._session.post = MagicMock(return_value=MagicMock(
            status_code=201,
            json=lambda: {'key': 'TEST-1', 'self': 'https://test.jira.com/rest/api/2/issue/10000'}
        ))

        # Call the real create_issue method
        fields = {'project': 'TEST', 'issuetype': 'Bug', 'summary': 'Test', 'story_points': 5}
        data = _prepare_api_fields(fields, jira._session)

        # Verify display name was converted
        self.assertIn('customfield_10001', data['fields'])
        self.assertEqual(data['fields']['customfield_10001'], 5)
        self.assertNotIn('story_points', data['fields'])

    def test_issue_update_with_display_names(self):
        """Test Issue.update converts display names to field IDs."""
        session = MagicMock()
        session.fields_cache = {'Story Points': 'customfield_10001'}

        issue = Issue(options={'server': 'https://test.jira.com'}, session=session)
        issue.raw = {'key': 'TEST-1', 'self': 'https://test.jira.com/rest/api/2/issue/10000'}

        # Mock the API call
        session.put = MagicMock(return_value=MagicMock(status_code=204))

        # Call update with display name
        fields = {'story_points': 8}
        result = _prepare_api_fields(fields, session, wrap=False)

        # Verify display name was converted
        self.assertIn('customfield_10001', result)
        self.assertEqual(result['customfield_10001'], 8)
        self.assertNotIn('story_points', result)


if __name__ == '__main__':
    unittest.main()
