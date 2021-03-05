# pylint: disable=E1103

"""
Run these tests: paver test_system -s lms -t edx_solutions_projects
"""
import uuid
from datetime import datetime
from urllib.parse import urlencode

import ddt
import pytz
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test.utils import override_settings
from edx_solutions_api_integration.models import GroupProfile
from edx_solutions_api_integration.test_utils import (
    APIClientMixin, CourseGradingMixin, SignalDisconnectTestMixin,
    make_non_atomic)
from edx_solutions_projects.models import Project, Workgroup
from mock import Mock, patch
from openedx.core.djangoapps.course_groups.cohorts import (
    delete_empty_cohort, get_cohort_by_name, get_course_cohort_names,
    is_user_in_cohort, remove_user_from_cohort)
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import (
    TEST_DATA_SPLIT_MODULESTORE, ModuleStoreEnum, ModuleStoreTestCase)
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory


@ddt.ddt
class WorkgroupsApiTests(SignalDisconnectTestMixin, ModuleStoreTestCase, APIClientMixin):

    """ Test suite for Workgroups API views """

    MODULESTORE = TEST_DATA_SPLIT_MODULESTORE

    def setUp(self):
        super().setUp()
        self.test_server_prefix = 'https://testserver'
        self.test_workgroups_uri = '/api/server/workgroups/'
        self.test_submissions_uri = '/api/server/submissions/'
        self.test_peer_reviews_uri = '/api/server/peer_reviews/'
        self.test_workgroup_reviews_uri = '/api/server/workgroup_reviews/'
        self.test_courses_uri = '/api/server/courses'
        self.test_bogus_course_id = 'foo/bar/baz'
        self.test_bogus_course_content_id = "i4x://foo/bar/baz"
        self.test_group_id = '1'
        self.test_bogus_group_id = "2131241123"
        self.test_workgroup_name = str(uuid.uuid4())

        self._create_course()

    def _create_course(self, store=ModuleStoreEnum.Type.split):
        with modulestore().default_store(store):
            self.test_course = CourseFactory.create(
                start=datetime(2014, 6, 16, 14, 30, tzinfo=pytz.UTC),
                end=datetime(2020, 1, 16, 14, 30, tzinfo=pytz.UTC),
                grading_policy={
                    "GRADER": [
                        {
                            "type": "Homework",
                            "min_count": 1,
                            "drop_count": 0,
                            "short_label": "HW",
                            "weight": 0.5
                        },
                    ],
                },
            )
            self.test_data = '<html>{}</html>'.format(str(uuid.uuid4()))

            self.test_group_project = ItemFactory.create(
                category="group-project",
                parent_location=self.test_course.location,
                due=datetime(2014, 5, 16, 14, 30, tzinfo=pytz.UTC),
                display_name="Group Project"
            )

            self.test_course_id = str(self.test_course.id)

            self.test_course_content_id = str(self.test_group_project.scope_ids.usage_id)

            self.test_group_name = str(uuid.uuid4())
            self.test_group = Group.objects.create(
                name=self.test_group_name
            )
            GroupProfile.objects.create(
                name=self.test_group_name,
                group_id=self.test_group.id,
                group_type="series"
            )

            self.test_project = Project.objects.create(
                course_id=self.test_course_id,
                content_id=self.test_course_content_id
            )

            self.test_project2 = Project.objects.create(
                course_id=self.test_course_id,
                content_id=str(self.test_group_project.scope_ids.usage_id)
            )

            self.test_user_email = str(uuid.uuid4())
            self.test_user_username = str(uuid.uuid4())
            self.test_user = User.objects.create(
                email=self.test_user_email,
                username=self.test_user_username
            )

            self.test_user_email2 = str(uuid.uuid4())
            self.test_user_username2 = str(uuid.uuid4())
            self.test_user2 = User.objects.create(
                email=self.test_user_email2,
                username=self.test_user_username2
            )

            CourseEnrollmentFactory.create(user=self.test_user, course_id=self.test_course.id)
            CourseEnrollmentFactory.create(user=self.test_user2, course_id=self.test_course.id)
            cache.clear()

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_list_post(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        self.assertGreater(response.data['id'], 0)
        confirm_uri = '{}{}{}/'.format(
            self.test_server_prefix,
            self.test_workgroups_uri,
            str(response.data['id'])
        )
        self.assertEqual(response.data['url'], confirm_uri)
        self.assertGreater(response.data['id'], 0)
        self.assertEqual(response.data['name'], self.test_workgroup_name)
        self.assertEqual(response.data['project'], self.test_project.id)
        self.assertIsNotNone(response.data['users'])
        self.assertIsNotNone(response.data['groups'])
        self.assertIsNotNone(response.data['submissions'])
        self.assertIsNotNone(response.data['workgroup_reviews'])
        self.assertIsNotNone(response.data['peer_reviews'])
        self.assertIsNotNone(response.data['created'])
        self.assertIsNotNone(response.data['modified'])

        # make sure a discussion cohort was created
        cohort_name = Workgroup.cohort_name_for_workgroup(
            self.test_project.id,
            response.data['id'],
            self.test_workgroup_name
        )
        cohort = get_cohort_by_name(self.test_course.id, cohort_name)
        self.assertIsNotNone(cohort)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_detail_get(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        confirm_uri = self.test_server_prefix + test_uri
        self.assertEqual(response.data['url'], confirm_uri)
        self.assertGreater(response.data['id'], 0)
        self.assertEqual(response.data['name'], self.test_workgroup_name)
        self.assertEqual(response.data['project'], self.test_project.id)
        self.assertIsNotNone(response.data['users'])
        self.assertIsNotNone(response.data['groups'])
        self.assertIsNotNone(response.data['submissions'])
        self.assertIsNotNone(response.data['workgroup_reviews'])
        self.assertIsNotNone(response.data['peer_reviews'])
        self.assertIsNotNone(response.data['created'])
        self.assertIsNotNone(response.data['modified'])

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_groups_post(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        groups_uri = '{}groups/'.format(test_uri)
        data = {"id": self.test_group.id}
        response = self.do_post(groups_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['groups'][0]['id'], self.test_group.id)
        self.assertEqual(response.data['groups'][0]['name'], self.test_group.name)

        test_groupnoprofile_name = str(uuid.uuid4())
        test_groupnoprofile = Group.objects.create(
            name=test_groupnoprofile_name
        )
        data = {"id": test_groupnoprofile.id}
        response = self.do_post(groups_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['groups'][1]['id'], test_groupnoprofile.id)
        self.assertEqual(response.data['groups'][1]['name'], test_groupnoprofile_name)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_groups_get(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        groups_uri = '{}groups/'.format(test_uri)
        data = {"id": self.test_group.id}
        response = self.do_post(groups_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(groups_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['id'], self.test_group.id)
        self.assertEqual(response.data[0]['name'], self.test_group.name)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_users_post(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['users'][0]['id'], self.test_user.id)

        # make sure a discussion cohort was created
        cohort_name = Workgroup.cohort_name_for_workgroup(
            self.test_project.id,
            response.data['id'],
            self.test_workgroup_name
        )
        cohort = get_cohort_by_name(self.test_course.id, cohort_name)
        self.assertIsNotNone(cohort)
        self.assertTrue(is_user_in_cohort(cohort, self.test_user.id))

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_users_post_preexisting_workgroup(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        data = {
            'name': "Workgroup 2",
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 400)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_users_post_preexisting_project(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        # Second project created in setUp, adding a new workgroup
        data = {
            'name': "Workgroup 2",
            'project': self.test_project2.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)

        # Assign the test user to the alternate project/workgroup
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 400)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_users_post_with_cohort_backfill(self, store):
        self._create_course(store)
        """
        This test asserts a case where a workgroup was created before the existence of a cohorted discussion
        """
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['users'][0]['id'], self.test_user.id)

        cohort_name = Workgroup.cohort_name_for_workgroup(
            self.test_project.id,
            response.data['id'],
            self.test_workgroup_name
        )

        # now let's remove existing cohort users
        cohort = get_cohort_by_name(self.test_course.id, cohort_name)
        self.assertTrue(is_user_in_cohort(cohort, self.test_user.id))

        remove_user_from_cohort(cohort, self.test_user.username)
        self.assertFalse(is_user_in_cohort(cohort, self.test_user.id))

        # delete cohort
        delete_empty_cohort(self.test_course.id, cohort_name)
        self.assertEqual(0, len(get_course_cohort_names(self.test_course.id)))

        # add a 2nd user and make sure a discussion cohort was created and users were backfilled
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user2.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        # now inspect cohort and assert that things are as we anticipate (i.e. both users are in there)
        cohort = get_cohort_by_name(self.test_course.id, cohort_name)
        self.assertIsNotNone(cohort)
        self.assertTrue(is_user_in_cohort(cohort, self.test_user.id))
        self.assertTrue(is_user_in_cohort(cohort, self.test_user2.id))

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_users_delete(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_workgroup_uri = response.data['url']
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        # Test if workgroup has exactly two users
        response = self.do_get(test_workgroup_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['users']), 1)

        # Enroll second user
        data = {"id": self.test_user2.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        # Test if workgroup has exactly two users
        response = self.do_get(test_workgroup_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['users']), 2)

        # Test deleting an invalid user from workgroup
        data = {"id": '345345344'}
        response = self.do_delete(users_uri, data)
        self.assertEqual(response.status_code, 400)

        # Test deleting an existing user from workgroup
        data = {"id": self.test_user.id}
        response = self.do_delete(users_uri, data)
        self.assertEqual(response.status_code, 204)
        response = self.do_get(test_workgroup_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['users']), 1)
        self.assertEqual(response.data['users'][0]['id'], self.test_user2.id)

        # Test deleting the last user from workgroup; the empty workgroup should get deleted too
        data = {"id": self.test_user2.id}
        response = self.do_delete(users_uri, data)
        self.assertEqual(response.status_code, 204)
        response = self.do_get(test_workgroup_uri)
        self.assertEqual(response.status_code, 404)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_users_get(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        users_uri = '{}users/'.format(test_uri)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        response = self.do_get(users_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['id'], self.test_user.id)
        self.assertEqual(response.data[0]['username'], self.test_user.username)
        self.assertEqual(response.data[0]['email'], self.test_user.email)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_peer_reviews_get(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']
        pr_data = {
            'workgroup': workgroup_id,
            'user': self.test_user.id,
            'reviewer': self.test_user.username,
            'question': 'Test question?',
            'answer': 'Test answer!',
            'content_id': self.test_course_content_id
        }
        response = self.do_post(self.test_peer_reviews_uri, pr_data)
        self.assertEqual(response.status_code, 201)
        pr1_id = response.data['id']
        pr_data = {
            'workgroup': workgroup_id,
            'user': self.test_user.id,
            'reviewer': self.test_user.username,
            'question': 'Test question2',
            'answer': 'Test answer2',
            'content_id': self.test_course_id
        }
        response = self.do_post(self.test_peer_reviews_uri, pr_data)
        self.assertEqual(response.status_code, 201)

        test_uri = '{}{}/'.format(self.test_workgroups_uri, workgroup_id)
        peer_reviews_uri = '{}peer_reviews/'.format(test_uri)
        response = self.do_get(peer_reviews_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['id'], pr1_id)
        self.assertEqual(response.data[0]['reviewer'], self.test_user.username)

        content_id = {"content_id": self.test_course_content_id}
        test_uri = '{}{}/peer_reviews/?{}'.format(self.test_workgroups_uri, workgroup_id, urlencode(content_id))
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], pr1_id)
        self.assertEqual(response.data[0]['reviewer'], self.test_user.username)

    @make_non_atomic
    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_workgroup_reviews_get(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']
        wr_data = {
            'workgroup': workgroup_id,
            'reviewer': self.test_user.username,
            'question': 'Test question?',
            'answer': 'Test answer!',
            'content_id': self.test_course_content_id
        }
        response = self.do_post(self.test_workgroup_reviews_uri, wr_data)
        self.assertEqual(response.status_code, 201)
        wr1_id = response.data['id']
        wr_data = {
            'workgroup': workgroup_id,
            'reviewer': self.test_user.username,
            'question': 'Test question?',
            'answer': 'Test answer!',
            'content_id': self.test_course_id
        }
        response = self.do_post(self.test_workgroup_reviews_uri, wr_data)
        self.assertEqual(response.status_code, 201)

        test_uri = '{}{}/'.format(self.test_workgroups_uri, workgroup_id)
        workgroup_reviews_uri = '{}workgroup_reviews/'.format(test_uri)
        response = self.do_get(workgroup_reviews_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['id'], wr1_id)
        self.assertEqual(response.data[0]['reviewer'], self.test_user.username)

        content_id = {"content_id": self.test_course_content_id}
        test_uri = '{}{}/workgroup_reviews/?{}'.format(self.test_workgroups_uri, workgroup_id, urlencode(content_id))
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], wr1_id)
        self.assertEqual(response.data[0]['reviewer'], self.test_user.username)

    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_submissions_get(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']
        data = {
            'workgroup': workgroup_id,
            'user': self.test_user.id,
            'document_id': 'filename.pdf',
            'document_url': 'https://s3.amazonaws.com/bucketname/filename.pdf',
            'document_mime_type': 'application/pdf'
        }
        response = self.do_post(self.test_submissions_uri, data)
        self.assertEqual(response.status_code, 201)
        submission_id = response.data['id']
        test_uri = '{}{}/'.format(self.test_workgroups_uri, workgroup_id)
        submissions_uri = '{}submissions/'.format(test_uri)
        response = self.do_get(submissions_uri)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['id'], submission_id)
        self.assertEqual(response.data[0]['user'], self.test_user.id)

    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_submissions_list_post_invalid_relationships(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))

        users_uri = '{}users/'.format(test_uri)
        data = {"id": 123456}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 400)

        groups_uri = '{}groups/'.format(test_uri)
        data = {"id": 123456}
        response = self.do_post(groups_uri, data)
        self.assertEqual(response.status_code, 400)

    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_detail_get_undefined(self, store):
        self._create_course(store)
        test_uri = '{}123456789/'.format(self.test_workgroups_uri)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)

    @ddt.data(ModuleStoreEnum.Type.split, ModuleStoreEnum.Type.mongo)
    def test_workgroups_detail_delete(self, store):
        self._create_course(store)
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        test_uri = '{}{}/'.format(self.test_workgroups_uri, str(response.data['id']))
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 200)
        response = self.do_delete(test_uri)
        self.assertEqual(response.status_code, 204)
        response = self.do_get(test_uri)
        self.assertEqual(response.status_code, 404)


@ddt.ddt
class WorkgroupsGradesApiTests(SignalDisconnectTestMixin, ModuleStoreTestCase, APIClientMixin, CourseGradingMixin):

    MODULESTORE = TEST_DATA_SPLIT_MODULESTORE

    def setUp(self):
        super().setUp()
        self.test_server_prefix = 'https://testserver'
        self.test_workgroups_uri = '/api/server/workgroups/'
        self.test_courses_uri = '/api/server/courses'

        self.test_course = self.setup_course_with_grading()
        self.test_data = '<html>{}</html>'.format(str(uuid.uuid4()))
        self.test_group_project = ItemFactory.create(
            category="group-project",
            parent_location=self.test_course.midterm_assignment.parent,
            graded=True,
            due=datetime(2014, 5, 16, 14, 30, tzinfo=pytz.UTC),
            display_name="Group Project"
        )

        self.test_course_id = str(self.test_course.id)
        self.test_course_content_id = str(self.test_group_project.scope_ids.usage_id)
        self.test_workgroup_name = str(uuid.uuid4())
        self.test_project = Project.objects.create(
            course_id=self.test_course_id,
            content_id=self.test_course_content_id
        )

        self.test_user = UserFactory.create()
        self.test_user2 = UserFactory.create()

        CourseEnrollmentFactory.create(user=self.test_user, course_id=self.test_course.id)
        CourseEnrollmentFactory.create(user=self.test_user2, course_id=self.test_course.id)
        cache.clear()

    def test_workgroups_grades_post(self):
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']
        users_uri = '{}{}/users/'.format(self.test_workgroups_uri, workgroup_id)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        data = {"id": self.test_user2.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        grade_data = {
            'course_id': self.test_course_id,
            'content_id': self.test_course_content_id,
            'grade': 0.85,
            'max_grade': 1,
        }
        grades_uri = '{}{}/grades/'.format(self.test_workgroups_uri, workgroup_id)
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 201)

        # Confirm the grades for the users
        course_grades_uri = '{}/{}/metrics/grades/'.format(self.test_courses_uri, self.test_course_id)
        response = self.do_get(course_grades_uri)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data['grades']), 0)

    def test_workgroups_grades_post_invalid_course(self):
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']
        users_uri = '{}{}/users/'.format(self.test_workgroups_uri, workgroup_id)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        data = {"id": self.test_user2.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        grade_data = {
            'course_id': 'really-invalid-course-id',
            'content_id': self.test_course_content_id,
            'grade': 0.85,
            'max_grade': 0.75,
        }
        grades_uri = '{}{}/grades/'.format(self.test_workgroups_uri, workgroup_id)
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

        grade_data = {
            'course_id': 'really-invalid-course-id',
            'content_id': self.test_course_content_id,
            'grade': 0.85,
            'max_grade': 0.75,
        }
        grades_uri = '{}{}/grades/'.format(self.test_workgroups_uri, workgroup_id)
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

    def test_workgroups_grades_post_invalid_course_content(self):
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']
        users_uri = '{}{}/users/'.format(self.test_workgroups_uri, workgroup_id)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        data = {"id": self.test_user2.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        grade_data = {
            'course_id': self.test_course_id,
            'content_id': 'bogus-content-id',
            'grade': 0.85,
            'max_grade': 0.75,
        }
        grades_uri = '{}{}/grades/'.format(self.test_workgroups_uri, workgroup_id)
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

    def test_workgroups_grades_post_invalid_requests(self):
        data = {
            'name': self.test_workgroup_name,
            'project': self.test_project.id
        }
        response = self.do_post(self.test_workgroups_uri, data)
        self.assertEqual(response.status_code, 201)
        workgroup_id = response.data['id']

        users_uri = '{}{}/users/'.format(self.test_workgroups_uri, workgroup_id)
        data = {"id": self.test_user.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)
        data = {"id": self.test_user2.id}
        response = self.do_post(users_uri, data)
        self.assertEqual(response.status_code, 201)

        grades_uri = '{}{}/grades/'.format(self.test_workgroups_uri, workgroup_id)
        grade_data = {
            'content_id': self.test_course_content_id,
            'grade': 0.85,
            'max_grade': 0.75,
        }
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

        grade_data = {
            'course_id': 'really-invalid-course-id',
            'content_id': self.test_course_content_id,
            'grade': 0.85,
            'max_grade': 0.75,
        }
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

        grade_data = {
            'course_id': self.test_course_id,
            'grade': 0.85,
            'max_grade': 0.75,
        }
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

        grade_data = {
            'course_id': self.test_course_id,
            'content_id': self.test_course_content_id,
            'max_grade': 0.75,
        }
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)

        grade_data = {
            'course_id': self.test_course_id,
            'content_id': self.test_course_content_id,
            'grade': 0.85,
        }
        response = self.do_post(grades_uri, grade_data)
        self.assertEqual(response.status_code, 400)
