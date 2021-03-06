# pylint: disable=E1101
"""
Run these tests: paver test_system -s lms -t edx_solutions_projects
"""
import uuid
from datetime import datetime

import pytz
from django.conf import settings
from django.test.utils import override_settings
from edx_solutions_projects import models
from xmodule.modulestore.django import SignalHandler
from xmodule.modulestore.tests.django_utils import (
    TEST_DATA_SPLIT_MODULESTORE, ModuleStoreTestCase)
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory


class ProjectsReceiversTests(ModuleStoreTestCase):
    """ Test suite for signal receivers """

    MODULESTORE = TEST_DATA_SPLIT_MODULESTORE
    ENABLED_SIGNALS = ['course_deleted']

    def setUp(self):
        super().setUp()
        # Create a course to work with
        self.course = CourseFactory.create(
            start=datetime(2014, 6, 16, 14, 30, tzinfo=pytz.UTC),
            end=datetime(2020, 1, 16, 14, 30, tzinfo=pytz.UTC)
        )
        test_data = '<html>{}</html>'.format(str(uuid.uuid4()))

        self.chapter = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            due=datetime(2014, 5, 16, 14, 30),
            display_name="Overview",
        )

    def test_receiver_on_course_deleted(self):
        project = models.Project.objects.create(
            course_id=str(self.course.id),
            content_id=str(self.chapter.location)
        )
        workgroup = models.Workgroup.objects.create(
            project=project,
            name='TEST WORKGROUP'
        )
        workgroup_user = models.WorkgroupUser.objects.create(
            workgroup=workgroup,
            user=self.user
        )
        workgroup_review = models.WorkgroupReview.objects.create(
            workgroup=workgroup,
            reviewer=self.user,
            question='test',
            answer='test',
            content_id=str(self.chapter.location),
        )
        workgroup_peer_review = models.WorkgroupPeerReview.objects.create(
            workgroup=workgroup,
            user=self.user,
            reviewer=self.user,
            question='test',
            answer='test',
            content_id=str(self.chapter.location),
        )
        workgroup_submission = models.WorkgroupSubmission.objects.create(
            workgroup=workgroup,
            user=self.user,
            document_id='test',
            document_url='test',
            document_mime_type='test',
        )
        workgroup_submission_review = models.WorkgroupSubmissionReview.objects.create(
            submission=workgroup_submission,
            reviewer=self.user,
            question='test',
            answer='test',
            content_id=str(self.chapter.location),
        )

        self.assertEqual(models.Project.objects.filter(id=project.id).count(), 1)
        self.assertEqual(models.Workgroup.objects.filter(id=workgroup.id).count(), 1)
        self.assertEqual(models.WorkgroupUser.objects.filter(id=workgroup_user.id).count(), 1)
        self.assertEqual(models.WorkgroupReview.objects.filter(id=workgroup_review.id).count(), 1)
        self.assertEqual(models.WorkgroupSubmission.objects.filter(id=workgroup_submission.id).count(), 1)
        self.assertEqual(models.WorkgroupSubmissionReview.objects.filter(id=workgroup_submission_review.id).count(), 1)
        self.assertEqual(models.WorkgroupPeerReview.objects.filter(id=workgroup_peer_review.id).count(), 1)

        # Run the data migration
        SignalHandler.course_deleted.send(sender=None, course_key=self.course.id)

        # Validate that the course references were removed
        self.assertEqual(models.Project.objects.filter(id=project.id).count(), 0)
        self.assertEqual(models.Workgroup.objects.filter(id=workgroup.id).count(), 0)
        self.assertEqual(models.WorkgroupUser.objects.filter(id=workgroup_user.id).count(), 0)
        self.assertEqual(models.WorkgroupReview.objects.filter(id=workgroup_review.id).count(), 0)
        self.assertEqual(models.WorkgroupSubmission.objects.filter(id=workgroup_submission.id).count(), 0)
        self.assertEqual(models.WorkgroupSubmissionReview.objects.filter(id=workgroup_submission_review.id).count(), 0)
        self.assertEqual(models.WorkgroupPeerReview.objects.filter(id=workgroup_peer_review.id).count(), 0)
