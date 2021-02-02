from django.core.management.base import BaseCommand

from edx_solutions_api_integration.courseware_access import get_course_key
from openedx.core.djangoapps.course_groups.models import CourseUserGroup, CohortMembership


class Command(BaseCommand):
    help = "Cohort fixation of specific courses"

    def add_arguments(self, parser):
        parser.add_argument('fix', nargs=1, type=str, help='Fix cohort')
        parser.add_argument('course', nargs='+', type=str, help='Cohort fixation courses')

    def handle(self, *args, **options):
        try:
            op = options['fix'][0]
            courses = options['course']
            if op.lower() != 'fix':
                raise Exception("Only 'fix' operations supported")

            course_keys = [get_course_key(course_id) for course_id in courses]
            if None in course_keys:
                raise Exception("At least one course failed to create course key")

            # Default cohort must exclude e.g default_cohort
            course_user_groups = CourseUserGroup.objects.filter(
                course_id__in=course_keys).exclude(
                name=CourseUserGroup.default_cohort_name
            ).values_list('id', flat=True)
            memberships = CohortMembership.objects.filter(
                course_user_group_id__in=list(course_user_groups),
                course_id__in=course_keys
            ).values_list(
                'user_id',
                'course_user_group_id'
            )

            total_fixed_members = 0
            GroupUserModel = CourseUserGroup.users.through._meta.model
            for user_id, course_user_group_id in memberships:
                member, created = GroupUserModel.objects.get_or_create(
                    courseusergroup_id=course_user_group_id, user_id=user_id
                )
                if created:
                    total_fixed_members += 1
        except Exception as e:
            self.stderr.write(self.style.ERROR('Task failed to trigger with exception: "%s"' % str(e)))
        else:
            self.stdout.write(self.style.SUCCESS('Successfully triggered cohort fixation task, '
                                                 'total fixed cohort members {}'.format(total_fixed_members)))
