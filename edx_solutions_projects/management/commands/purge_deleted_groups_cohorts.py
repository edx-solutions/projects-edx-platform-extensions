from django.core.management.base import BaseCommand
from edx_solutions_api_integration.courseware_access import get_course_key
from edx_solutions_projects.models import Workgroup
from openedx.core.djangoapps.course_groups.models import CourseUserGroup


class Command(BaseCommand):
    help = "Cohort deletion of course deleted groups"

    def add_arguments(self, parser):
        parser.add_argument('remove', nargs=1, type=str, help='Remove cohort')
        parser.add_argument('course', nargs='+', type=str, help='Cohort deletion course')

    def handle(self, *args, **options):
        try:
            op = options['remove'][0]
            courses = options['course']
            if op.lower() != 'remove':
                raise Exception("Only 'remove' operations supported")

            course_keys = [get_course_key(course_id) for course_id in courses]
            if None in course_keys:
                raise Exception("At least one course failed to create course key")

            # Default cohort must exclude e.g default_cohort
            exclude_cohorts = [CourseUserGroup.default_cohort_name]
            workgroups = Workgroup.objects.filter(project__course_id__in=courses)
            for work_group in workgroups:
                exclude_cohorts.append(work_group.cohort_name)
            obsoleted_cohorts = CourseUserGroup.objects.filter(
                course_id__in=course_keys,
                group_type=CourseUserGroup.COHORT
            ).exclude(name__in=exclude_cohorts)
            obsoleted_cohorts.delete()
        except Exception as e:
            self.stderr.write(self.style.ERROR('Task failed to trigger with exception: "%s"' % str(e)))
        else:
            self.stdout.write(self.style.SUCCESS('Successfully triggered Cohort deletion for course deleted groups'))
