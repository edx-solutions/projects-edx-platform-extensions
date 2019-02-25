"""
Signal handlers supporting various gradebook use cases
"""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from util.signals import course_deleted

from edx_solutions_projects import models
from edx_solutions_projects.models import WorkgroupSubmission


@receiver(course_deleted)
def on_course_deleted(sender, **kwargs):  # pylint: disable=W0613
    """
    Listens for a 'course_deleted' signal and when observed
    removes model entries for the specified course
    """
    course_key = kwargs.get('course_key')
    if course_key:
        projects = models.Project.objects.filter(course_id=unicode(course_key))
        for project in projects:
            workgroups = models.Workgroup.objects.filter(project=project)
            for workgroup in workgroups:
                submissions = models.WorkgroupSubmission.objects.filter(workgroup=workgroup)
                for submission in submissions:
                    submission_reviews = models.WorkgroupSubmissionReview.objects.filter(submission=submission)
                    for submission_review in submission_reviews:
                        models.WorkgroupSubmissionReview.objects.filter(id=submission_review.id).delete()
                    models.WorkgroupSubmission.objects.filter(id=submission.id).delete()
                models.WorkgroupPeerReview.objects.filter(workgroup=workgroup).delete()
                models.WorkgroupReview.objects.filter(workgroup=workgroup).delete()
                models.WorkgroupUser.objects.filter(workgroup=workgroup).delete()
                models.Workgroup.objects.filter(id=workgroup.id).delete()
            models.Project.objects.filter(id=project.id).delete()


@receiver(post_delete, sender=WorkgroupSubmission)
def reassign_or_delete_image(instance, **_kwargs):
    """Reassigns image if user is deleted and there are more users in the workgroup."""
    explicit_deletion = instance.workgroup.users.filter(id=instance.user.id).exists()
    next_user = instance.workgroup.users.first()
    if next_user and not explicit_deletion:
        instance.user = next_user
        instance.save()
    else:
        instance.delete_file()
