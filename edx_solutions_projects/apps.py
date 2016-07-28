"""
Application configuration/registry module
https://docs.djangoproject.com/en/1.10/ref/applications/#configuring-applications
"""
from django.apps import AppConfig


class SolutionsAppProjectsConfig(AppConfig):
    """
    Application configuration class.
    It overrides `ready` method to register signals.
    """
    name = 'edx_solutions_projects'
    verbose_name = 'projects for work groups'

    def ready(self):

        # import signal handlers
        import edx_solutions_projects.receivers  # pylint: disable=unused-import
