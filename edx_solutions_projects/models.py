""" Database ORM models managed by this Django app """

from urllib.parse import unquote, urlparse

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models
from model_utils.models import TimeStampedModel


class Project(TimeStampedModel):
    """
    Model representing the Project concept.  Projects are an
    intersection of Courses, CourseContent, and Workgroups.
    """
    course_id = models.CharField(max_length=255)
    content_id = models.CharField(max_length=255)
    organization = models.ForeignKey(
        'edx_solutions_organizations.Organization',
        blank=True,
        null=True,
        related_name="projects",
        on_delete=models.SET_NULL
    )

    class Meta:
        """ Meta class for defining additional model characteristics """
        unique_together = ("course_id", "content_id", "organization")

    @classmethod
    def get_user_ids_in_project_by_content_id(cls, course_id, content_id):
        """
        Returns a database cursor for all users associated with a project
        specified by a content_id
        """

        query = Project.objects.select_related('workgroups__users').values_list('workgroups__users', flat=True).filter(
            course_id=course_id,
            content_id=content_id
        )

        return query


class Workgroup(TimeStampedModel):
    """
    Model representing the Workgroup concept.  Workgroups are an
    intersection of Users and CourseContent, although they can also be
    related to other Groups.
    """
    name = models.CharField(max_length=255, null=True, blank=True)
    project = models.ForeignKey(Project, related_name="workgroups", on_delete=models.CASCADE)
    users = models.ManyToManyField(User, related_name="workgroups", through="WorkgroupUser", blank=True)
    groups = models.ManyToManyField(Group, related_name="workgroups", blank=True)

    @property
    def cohort_name(self):
        return Workgroup.cohort_name_for_workgroup(
            self.project.id,
            self.id,
            self.name
        )

    @classmethod
    def cohort_name_for_workgroup(cls, project_id, workgroup_id, workgroup_name):
        return 'Group Project {} Workgroup {} ({})'.format(
            project_id,
            workgroup_id,
            workgroup_name
        )

    def add_user(self, user):
        workgroup_user = WorkgroupUser(workgroup=self, user=user)
        workgroup_user.save()

    def remove_user(self, user):
        workgroup_user = WorkgroupUser.objects.get(workgroup=self, user=user)
        workgroup_user.delete()

    @classmethod
    def get_user_ids_in_workgroup(cls, workgroup_id):
        """
        Returns a database cursor for all users associated with a project
        specified by a content_id
        """

        query = Workgroup.objects.select_related('users').values_list('users', flat=True).filter(
            id=workgroup_id
        )

        return query


class WorkgroupUser(models.Model):
    """A Folder to store some data between a client and its insurance"""

    workgroup = models.ForeignKey(Workgroup, null=False, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=False, on_delete=models.CASCADE)

    class Meta:
        db_table = 'edx_solutions_projects_workgroup_users'

    def clean(self):
        # Ensure the user is not already assigned to a workgroup for this course
        existing_workgroups = Workgroup.objects.filter(users=self.user).filter(project__course_id=self.workgroup.project.course_id)
        if len(existing_workgroups):
            raise ValidationError('User {} is already assigned to a workgroup for this course'.format(self.user.username))

    def save(self, **kwargs):
        self.clean()
        return super().save(**kwargs)


class WorkgroupReview(TimeStampedModel):
    """
    Model representing the Workgroup Review concept.  A Workgroup Review is
    a single question/answer combination for a particular Workgroup in the
    context of a specific Project, as defined in the Group Project XBlock
    schema.  There can be more than one Project Review entry for a given Project.
    """
    workgroup = models.ForeignKey(Workgroup, related_name="workgroup_reviews", on_delete=models.CASCADE)
    reviewer = models.CharField(max_length=255)  # AnonymousUserId
    question = models.CharField(max_length=1024)
    answer = models.TextField()
    content_id = models.CharField(max_length=255, null=True, blank=True)


class WorkgroupSubmission(TimeStampedModel):
    """
    Model representing the Submission concept.  A Submission is a project artifact
    created by the Users in a Workgroup.  The document fields are defined by the
    'Group Project' XBlock and data for a specific instance is persisted here
    """
    workgroup = models.ForeignKey(Workgroup, related_name="submissions", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="submissions", on_delete=models.DO_NOTHING)
    document_id = models.CharField(max_length=255)
    document_url = models.CharField(max_length=2048)
    document_mime_type = models.CharField(max_length=255)
    document_filename = models.CharField(max_length=255, blank=True, null=True)

    @property
    def document_path(self):
        """
        :return: the path to the document in default storage
        """
        return urlparse(unquote(self.document_url)).path.lstrip('/media/')

    def delete_file(self):
        """
        Delete uploaded file before deleting the submission.
        """
        default_storage.delete(self.document_path)


class WorkgroupSubmissionReview(TimeStampedModel):
    """
    Model representing the Submission Review concept.  A Submission Review is
    essentially a single question/answer combination for a particular Submission,
    defined in the Group Project XBlock schema.  There can be more than one
    Submission Review entry for a given Submission.
    """
    submission = models.ForeignKey(WorkgroupSubmission, related_name="reviews", on_delete=models.CASCADE)
    reviewer = models.CharField(max_length=255)  # AnonymousUserId
    question = models.CharField(max_length=1024)
    answer = models.TextField()
    content_id = models.CharField(max_length=255, null=True, blank=True)


class WorkgroupPeerReview(TimeStampedModel):
    """
    Model representing the Peer Review concept.  A Peer Review is a record of a
    specific question/answer defined in the Group Project XBlock schema.  There
    can be more than one Peer Review entry for a given User.
    """
    workgroup = models.ForeignKey(Workgroup, related_name="peer_reviews", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="workgroup_peer_reviewees", on_delete=models.CASCADE)
    reviewer = models.CharField(max_length=255)  # AnonymousUserId
    question = models.CharField(max_length=1024)
    answer = models.TextField()
    content_id = models.CharField(max_length=255, null=True, blank=True)
