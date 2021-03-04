# pylint: disable=E1103

"""
Run these tests: paver test_system -s lms -t edx_solutions_projects
"""
import uuid

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from edx_solutions_api_integration.test_utils import APIClientMixin
from edx_solutions_projects.models import Project, Workgroup
from edx_solutions_projects.scope_resolver import GroupProjectParticipantsScopeResolver


class ProjectsApiTests(TestCase, APIClientMixin):

    """ Test suite for Projects API views """

    def setUp(self):
        super().setUp()
        self.test_server_prefix = 'https://testserver'
        self.test_projects_uri = '/api/server/projects/'
        self.test_organizations_uri = '/api/server/organizations/'
        self.test_project_name = str(uuid.uuid4())

        self.test_course_id = 'edx/demo/course'
        self.test_bogus_course_id = 'foo/bar/baz'
        self.test_course_content_id = "i4x://blah"
        self.test_course_content_id2 = "i4x://blah2"
        self.test_bogus_course_content_id = "14x://foo/bar/baz"

        self.test_user = User.objects.create(
            email="test@edx.org",
            username="testing",
            is_active=True
        )

        self.test_user2 = User.objects.create(
            email="test2@edx.org",
            username="testing2",
            is_active=True
        )

        self.test_project = Project.objects.create(
            course_id=self.test_course_id,
            content_id=self.test_course_content_id,
        )

        self.test_project2 = Project.objects.create(
            course_id=self.test_course_id,
            content_id=self.test_course_content_id2,
        )

        self.test_workgroup = Workgroup.objects.create(
            name="Test Workgroup",
            project=self.test_project,
        )
        self.test_workgroup.add_user(self.test_user)
        self.test_workgroup.save()

        self.test_workgroup2 = Workgroup.objects.create(
            name="Test Workgroup2",
            project=self.test_project,
        )
        self.test_workgroup2.add_user(self.test_user2)
        self.test_workgroup2.save()

        cache.clear()

    def test_projects_list_get(self):
        """ Tests simple GET request - should return all projects """
        response = self.do_get(self.test_projects_uri)
        projects = response.data['results']
        self.assertEqual(len(projects), 2)
        project1, project2 = projects[0], projects[1]
        self.assertEqual(project1['id'], self.test_project.id)
        self.assertEqual(project1['course_id'], self.test_project.course_id)
        self.assertEqual(project1['content_id'], self.test_project.content_id)

        self.assertEqual(project2['id'], self.test_project2.id)
        self.assertEqual(project2['course_id'], self.test_project2.course_id)
        self.assertEqual(project2['content_id'], self.test_project2.content_id)

    def test_projects_list_get_filter_by_content_id(self):
        """ Tests GET request with specified content_id - should return single project with matching content_id """
        filter1 = {'course_id': self.test_project.course_id, 'content_id': self.test_project.content_id}
        response = self.do_get(self.test_projects_uri, query_parameters=filter1)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.test_project.id)
        self.assertEqual(response.data['results'][0]['content_id'], self.test_project.content_id)
        self.assertEqual(response.data['results'][0]['course_id'], self.test_project.course_id)

        filter2 = {'course_id': self.test_project2.course_id, 'content_id': self.test_project2.content_id}
        response = self.do_get(self.test_projects_uri, query_parameters=filter2)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], self.test_project2.id)
        self.assertEqual(response.data['results'][0]['content_id'], self.test_project2.content_id)
        self.assertEqual(response.data['results'][0]['course_id'], self.test_project2.course_id)

    def test_projects_list_incorrect_filter_request(self):
        """ Tests that GET requests with invalid filter returns BAD REQUEST response """
        def assert_request_failed(response):
            """ Assertion helper """
            self.assertEqual(response.status_code, 400)
            self.assertIn("detail", response.data)

        assert_request_failed(
            self.do_get(self.test_projects_uri, query_parameters={'course_id': self.test_project.course_id})
        )
        assert_request_failed(
            self.do_get(self.test_projects_uri, query_parameters={'content_id': self.test_project.content_id})
        )
        assert_request_failed(
            self.do_get(
                self.test_projects_uri, query_parameters={'content_id': "", 'course_id': self.test_project.course_id}
            )
        )
        assert_request_failed(
            self.do_get(
                self.test_projects_uri, query_parameters={'content_id': self.test_project.content_id, 'course_id': ""}
            )
        )

    def test_projects_list_post(self):
        data = {
            'name': 'Test Organization'
        }
        response = self.do_post(self.test_organizations_uri, data)
        self.assertEqual(response.status_code, 201)
        test_org_id = response.data['id']

        test_course_content_id = "i4x://blahblah1234"
        data = {
            'name': self.test_project_name,
            'course_id': self.test_course_id,
            'content_id': test_course_content_id,
            'organization': test_org_id
        }
        response = self.do_post(self.test_projects_uri, data)
        self.assertEqual(response.status_code, 201)
        self.assertGreater(response.data['id'], 0)
        confirm_uri = '{}{}{}/'.format(
            self.test_server_prefix,
            self.test_projects_uri,
            str(response.data['id'])
        )
        self.assertEqual(response.data['url'], confirm_uri)
        self.assertEqual(response.data['organization'], test_org_id)
        self.assertEqual(response.data['course_id'], self.test_course_id)
        self.assertEqual(response.data['content_id'], test_course_content_id)
        self.assertIsNotNone(response.data['workgroups'])
        self.assertIsNotNone(response.data['created'])
        self.assertIsNotNone(response.data['modified'])

    def test_projects_list_post_without_org(self):
        test_course_content_id = "i4x://blahblah1234"
        data = {
            'name': self.test_project_name,
            'course_id': self.test_course_id,
            'content_id': test_course_content_id,
        }
        response = self.do_post(self.test_projects_uri, data)
        self.assertEqual(response.status_code, 201)
        self.assertGreater(response.data['id'], 0)
        self.assertEqual(response.data['organization'], None)

    def test_projects_detail_get(self):
        test_uri = '{}{}/'.format(self.test_projects_uri, self.test_project.id)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['url'], confirm_uri)
        self.assertGreater(response.data['id'], 0)
        self.assertEqual(response.data['course_id'], self.test_course_id)
        self.assertEqual(response.data['content_id'], self.test_course_content_id)
        self.assertIsNotNone(response.data['workgroups'])
        self.assertIsNotNone(response.data['created'])
        self.assertIsNotNone(response.data['modified'])

    def test_projects_workgroups_post(self):
        test_uri = '{}{}/workgroups/'.format(self.test_projects_uri, self.test_project.id)
        data = {"id": self.test_workgroup.id}
        response = self.do_post(test_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['id'], self.test_workgroup.id)

    def test_projects_workgroups_post_invalid_workgroup(self):
        test_uri = '{}{}/workgroups/'.format(self.test_projects_uri, self.test_project.id)
        data = {
            'id': 123456,
        }
        response = self.do_post(test_uri, data)
        self.assertEqual(response.status_code, 400)

    def test_projects_detail_get_undefined(self):
        test_uri = '{}/123456789/'.format(self.test_projects_uri)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_projects_detail_delete(self):
        test_uri = '{}{}/'.format(self.test_projects_uri, self.test_project.id)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        response = self.do_delete(test_uri)
        self.assertEqual(response.status_code, 204)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    def test_get_user_ids(self):
        cursor = Project.get_user_ids_in_project_by_content_id(
            self.test_course_id,
            self.test_course_content_id
        )

        user_ids = [user_id for user_id in cursor.all()]

        self.assertEqual(len(user_ids), 2)
        self.assertIn(self.test_user.id, user_ids)
        self.assertIn(self.test_user2.id, user_ids)

    def test_get_workgroup_user_ids(self):
        cursor = Workgroup.get_user_ids_in_workgroup(self.test_workgroup.id)
        user_ids = [user_id for user_id in cursor.all()]
        self.assertEqual(len(user_ids), 1)
        self.assertIn(self.test_user.id, user_ids)

        cursor = Workgroup.get_user_ids_in_workgroup(self.test_workgroup2.id)
        user_ids = [user_id for user_id in cursor.all()]
        self.assertEqual(len(user_ids), 1)
        self.assertIn(self.test_user2.id, user_ids)

    def test_scope_resolver(self):
        cursor = GroupProjectParticipantsScopeResolver().resolve(
            'group_project_participants',
            {
                'course_id': self.test_course_id,
                'content_id': self.test_course_content_id
            },
            None
        )

        user_ids = [user_id for user_id in cursor.all()]

        self.assertEqual(len(user_ids), 2)
        self.assertIn(self.test_user.id, user_ids)
        self.assertIn(self.test_user2.id, user_ids)

    def test_workgroup_scope_resolver(self):
        cursor = GroupProjectParticipantsScopeResolver().resolve(
            'group_project_workgroup',
            {
                'workgroup_id': self.test_workgroup.id,
            },
            None
        )

        user_ids = [user_id for user_id in cursor.all()]

        self.assertEqual(len(user_ids), 1)
        self.assertIn(self.test_user.id, user_ids)

        cursor = GroupProjectParticipantsScopeResolver().resolve(
            'group_project_workgroup',
            {
                'workgroup_id': self.test_workgroup2.id,
            },
            None
        )

        user_ids = [user_id for user_id in cursor.all()]

        self.assertEqual(len(user_ids), 1)
        self.assertIn(self.test_user2.id, user_ids)
