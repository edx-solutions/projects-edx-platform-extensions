# pylint: disable=E1103

"""
Run these tests: paver test_system -s lms -t edx_solutions_projects
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from mock import patch

from edx_solutions_projects.models import Project, Workgroup
from edx_solutions_api_integration.test_utils import APIClientMixin


class SubmissionsApiTests(TestCase, APIClientMixin):

    """ Test suite for Submissions API views """

    def setUp(self):
        super(SubmissionsApiTests, self).setUp()
        self.test_server_prefix = 'https://testserver'
        self.test_users_uri = '/api/server/users/'
        self.test_workgroups_uri = '/api/server/workgroups/'
        self.test_projects_uri = '/api/server/projects/'
        self.test_submissions_uri = '/api/server/submissions/'

        self.test_course_id = 'edx/demo/course'
        self.test_bogus_course_id = 'foo/bar/baz'
        self.test_course_content_id = "i4x://blah"
        self.test_bogus_course_content_id = "14x://foo/bar/baz"

        self.test_document_id = "Document12345.pdf"
        self.test_document_url = "http://test-s3.amazonaws.com/bucketname"
        self.test_document_mime_type = "application/pdf"
        self.test_document_filename = "Test PDF Document"

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

        self.test_workgroup = Workgroup.objects.create(
            name="Test Workgroup",
            project=self.test_project,
        )
        self.test_workgroup.add_user(self.test_user)
        self.test_workgroup.add_user(self.test_user2)
        self.test_workgroup.save()

        cache.clear()

    @patch('edx_solutions_projects.serializers.WorkgroupSubmissionSerializer.get_document_url')
    def test_submissions_list_post(self, mock_get_document_url):
        submission_data = {
            'user': self.test_user.id,
            'workgroup': self.test_workgroup.id,
            'document_id': self.test_document_id,
            'document_url': self.test_document_url,
            'document_mime_type': self.test_document_mime_type,
        }
        mock_get_document_url.return_value = self.test_document_url
        response = self.do_post(self.test_submissions_uri, submission_data)
        self.assertEqual(response.status_code, 201)
        self.assertGreater(response.data['id'], 0)
        confirm_uri = '{}{}{}/'.format(
            self.test_server_prefix,
            self.test_submissions_uri,
            str(response.data['id'])
        )

        self.assertEqual(response.data['url'], confirm_uri)
        self.assertGreater(response.data['id'], 0)
        self.assertEqual(response.data['user'], self.test_user.id)
        self.assertEqual(response.data['workgroup'], self.test_workgroup.id)
        self.assertEqual(response.data['document_id'], self.test_document_id)
        self.assertEqual(response.data['document_url'], self.test_document_url)
        self.assertEqual(response.data['document_mime_type'], self.test_document_mime_type)
        self.assertIsNotNone(response.data['reviews'])
        self.assertIsNotNone(response.data['created'])
        self.assertIsNotNone(response.data['modified'])

    def test_submissions_list_post_invalid_relationships(self):
        submission_data = {
            'user': 123456,
            'workgroup': self.test_workgroup.id,
            'document_id': self.test_document_id,
            'document_url': self.test_document_url,
            'document_mime_type': self.test_document_mime_type,
            'document_filename': self.test_document_filename,
        }
        response = self.do_post(self.test_submissions_uri, submission_data)
        self.assertEqual(response.status_code, 400)

        submission_data = {
            'user': self.test_user.id,
            'workgroup': 123456,
            'document_id': self.test_document_id,
            'document_url': self.test_document_url,
            'document_mime_type': self.test_document_mime_type,
            'document_filename': self.test_document_filename,
        }
        response = self.do_post(self.test_submissions_uri, submission_data)
        self.assertEqual(response.status_code, 400)

    @patch('edx_solutions_projects.serializers.WorkgroupSubmissionSerializer.get_document_url')
    def test_submissions_detail_get(self, mock_get_document_url):
        submission_data = {
            'user': self.test_user.id,
            'workgroup': self.test_workgroup.id,
            'document_id': self.test_document_id,
            'document_url': self.test_document_url,
            'document_mime_type': self.test_document_mime_type,
            'document_filename': self.test_document_filename,
        }
        mock_get_document_url.return_value = self.test_document_url

        response = self.do_post(self.test_submissions_uri, submission_data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_submissions_uri, str(response.data['id']))
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        confirm_uri = '{}{}{}/'.format(
            self.test_server_prefix,
            self.test_submissions_uri,
            str(response.data['id'])
        )

        self.assertEqual(response.data['url'], confirm_uri)
        self.assertGreater(response.data['id'], 0)
        self.assertEqual(response.data['user'], self.test_user.id)
        self.assertEqual(response.data['workgroup'], self.test_workgroup.id)
        self.assertEqual(response.data['document_id'], self.test_document_id)
        self.assertEqual(response.data['document_url'], self.test_document_url)
        self.assertEqual(response.data['document_mime_type'], self.test_document_mime_type)
        self.assertEqual(response.data['document_filename'], self.test_document_filename)
        self.assertIsNotNone(response.data['reviews'])
        self.assertIsNotNone(response.data['created'])
        self.assertIsNotNone(response.data['modified'])

    def test_submissions_detail_get_undefined(self):
        test_uri = '{}123456789/'.format(self.test_submissions_uri)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    @patch('edx_solutions_projects.models.WorkgroupSubmission.delete_file')
    def test_submissions_detail_delete(self, delete_file):
        """Check deleting submission. Its file should be deleted too."""
        submission_data = {
            'user': self.test_user.id,
            'workgroup': self.test_workgroup.id,
            'document_id': self.test_document_id,
            'document_url': self.test_document_url,
            'document_mime_type': self.test_document_mime_type,
            'document_filename': self.test_document_filename,
        }
        response = self.do_post(self.test_submissions_uri, submission_data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_submissions_uri, str(response.data['id']))
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        response = self.do_delete(test_uri)
        self.assertEqual(response.status_code, 204)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

        # Check if file has been deleted too
        self.assertEqual(delete_file.call_count, 1)

    @patch('edx_solutions_projects.models.WorkgroupSubmission.delete_file')
    def test_submissions_reassigned_on_user_delete(self, mock_delete_file):
        """Test if removing the submission's owner causes its reassignment to another workgroup member."""
        submission_data = {
            'user': self.test_user.id,
            'workgroup': self.test_workgroup.id,
            'document_id': self.test_document_id,
            'document_url': self.test_document_url,
            'document_mime_type': self.test_document_mime_type,
            'document_filename': self.test_document_filename,
        }
        response = self.do_post(self.test_submissions_uri, submission_data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_submissions_uri, str(response.data['id']))

        # Check if submission is reassigned after removing the first user
        self.test_workgroup.remove_user(self.test_user)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user'], self.test_user2.id)

        # Check if submission is deleted after removing the second user
        self.test_workgroup.remove_user(self.test_user2)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

        # Check if file has been deleted too
        self.assertEqual(mock_delete_file.call_count, 1)
