"""
Tests for rename_projects_app command
"""
from mock import patch, Mock, PropertyMock
from datetime import datetime

from south.db import db
from south.models import MigrationHistory
from django.db import models, connection
from django.test import TestCase
from django.core.management import call_command
from django.contrib.contenttypes.models import ContentType


class RenameProjectsAppTests(TestCase):
    """
    Test suite for renaming projects app related database tables
    """
    def setUp(self):
        super(RenameProjectsAppTests, self).setUp()

        self.old_appname = 'old_dummy_app'
        self.new_appname = 'new_dummy_app'
        self.table_names = [
            'project',
            'workgroup',
            'workgroup_groups',
            'workgroup_users',
            'workgrouppeerreview',
            'workgroupreview',
            'workgroupsubmission',
            'workgroupsubmissionreview',
        ]

        self.old_app_migration_history = MigrationHistory.objects.create(
            app_name=self.old_appname,
            migration='0001_initial',
            applied=datetime.now()
        )
        self.old_app_content_type = ContentType.objects.create(
            app_label=self.old_appname,
            name='dummy model',
            model='dummymodel'
        )

        for table_name in self.table_names:
            db.create_table('{app_name}_{table_name}'.format(app_name=self.old_appname, table_name=table_name), (
                ('id', models.AutoField(primary_key=True)),
                ('name', models.CharField(unique=True, max_length=50)),
            ))

    def table_exists(self, table_name):
        """
        Checks if table exists in database
        """
        tables = connection.introspection.table_names()

        return table_name in tables

    def test_rename_organizations_app(self):
        """
        Test the organizations renaming
        """
        for table_name in self.table_names:
            self.assertEqual(
                self.table_exists('{app_name}_{table_name}'.format(app_name=self.old_appname, table_name=table_name)),
                True
            )

        self.assertEqual(MigrationHistory.objects.filter(app_name=self.old_appname).count(), 1)
        self.assertEqual(MigrationHistory.objects.filter(app_name=self.new_appname).count(), 0)
        self.assertEqual(ContentType.objects.filter(app_label=self.old_appname).count(), 1)
        self.assertEqual(ContentType.objects.filter(app_label=self.new_appname).count(), 0)

        with patch('edx_solutions_projects.management.commands.rename_projects_app.Command.old_appname', new_callable=PropertyMock) as mock_old_app, \
            patch('edx_solutions_projects.management.commands.rename_projects_app.Command.new_appname', new_callable=PropertyMock) as mock_new_app:  # pylint: disable=line-too-long
            mock_old_app.return_value = self.old_appname
            mock_new_app.return_value = self.new_appname
            call_command('rename_projects_app')

        for table_name in self.table_names:
            self.assertEqual(
                self.table_exists('{app_name}_{table_name}'.format(app_name=self.old_appname, table_name=table_name)),
                False
            )

        for table_name in self.table_names:
            self.assertEqual(
                self.table_exists('{app_name}_{table_name}'.format(app_name=self.new_appname, table_name=table_name)),
                True
            )

        self.assertEqual(MigrationHistory.objects.filter(app_name=self.old_appname).count(), 0)
        self.assertEqual(MigrationHistory.objects.filter(app_name=self.new_appname).count(), 1)
        self.assertEqual(ContentType.objects.filter(app_label=self.old_appname).count(), 0)
        self.assertEqual(ContentType.objects.filter(app_label=self.new_appname).count(), 1)
