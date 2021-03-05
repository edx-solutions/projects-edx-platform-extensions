"""
Management command to remove spurious workgroup submissions of image.png files
created due to an issue in xblock-group-project-v2 before v0.4.9 where it would
upload the image component of anything copied into the clipboard.
"""
import logging

from django.core.management.base import BaseCommand
from edx_solutions_projects.models import WorkgroupSubmission

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Removes spurious spurious workgroup submissions containing "image.png" due
    to an issue in xblock-group-project-v2 < v0.4.9
    """
    help = 'Removes spurious workgroup submissions containing "image.png"'

    def handle(self, *args, **options):
        log.info('Deleting workgroup submissions containing a document called "image.png"')

        choice = input('Are you sure? [yn]').lower()
        if choice == 'y' or choice == 'yes':
            WorkgroupSubmission.objects.filter(
                document_filename='image.png',
            ).delete()

            log.info('Done.')
