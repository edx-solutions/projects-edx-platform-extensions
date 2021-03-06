"""
Signal handlers supporting various gradebook use cases
"""
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from edx_solutions_projects import models
from edx_solutions_projects.models import WorkgroupSubmission, WorkgroupUser
from xmodule.modulestore.django import SignalHandler


@receiver(SignalHandler.course_deleted)
def on_course_deleted(sender, **kwargs):  # pylint: disable=W0613
    """
    Listens for a 'course_deleted' signal and when observed
    removes model entries for the specified course
    """
    course_key = kwargs.get('course_key')
    if course_key:
        projects = models.Project.objects.filter(course_id=str(course_key))
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


@receiver(pre_delete, sender=WorkgroupUser)
def reassign_or_delete_submissions(instance, **_kwargs):
    """Reassigns submissions if user is deleted and there are more users in the workgroup. Otherwise deletes them."""
    submissions = instance.user.submissions.all()
    next_user = instance.workgroup.users.exclude(id=instance.user.id).first()

    if next_user:
        # Reassign submissions
        for submission in submissions:
            submission.user = next_user
            submission.save()
    else:
        # Remove submissions
        submissions.delete()


@receiver(post_delete, sender=WorkgroupUser)
def delete_empty_workgroup(instance, **_kwargs):
    """Delete workgroup after deleting its last participant."""
    workgroup = instance.workgroup
    if workgroup.users.count() == 0:
        workgroup.delete()


@receiver(post_delete, sender=WorkgroupSubmission)
def delete_submission_file(instance, **_kwargs):
    """Delete submission file when submission is deleted"""
    instance.delete_file()
