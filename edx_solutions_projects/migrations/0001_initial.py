# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('edx_solutions_organizations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auth', '0006_require_contenttypes_0002'),
    ]

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('course_id', models.CharField(max_length=255)),
                ('content_id', models.CharField(max_length=255)),
                ('organization', models.ForeignKey(related_name='projects', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='edx_solutions_organizations.Organization', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Workgroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('name', models.CharField(max_length=255, null=True, blank=True)),
                ('groups', models.ManyToManyField(related_name='workgroups', to='auth.Group', blank=True)),
                ('project', models.ForeignKey(related_name='workgroups', to='edx_solutions_projects.Project')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkgroupPeerReview',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('reviewer', models.CharField(max_length=255)),
                ('question', models.CharField(max_length=1024)),
                ('answer', models.TextField()),
                ('content_id', models.CharField(max_length=255, null=True, blank=True)),
                ('user', models.ForeignKey(related_name='workgroup_peer_reviewees', to=settings.AUTH_USER_MODEL)),
                ('workgroup', models.ForeignKey(related_name='peer_reviews', to='edx_solutions_projects.Workgroup')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkgroupReview',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('reviewer', models.CharField(max_length=255)),
                ('question', models.CharField(max_length=1024)),
                ('answer', models.TextField()),
                ('content_id', models.CharField(max_length=255, null=True, blank=True)),
                ('workgroup', models.ForeignKey(related_name='workgroup_reviews', to='edx_solutions_projects.Workgroup')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkgroupSubmission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('document_id', models.CharField(max_length=255)),
                ('document_url', models.CharField(max_length=2048)),
                ('document_mime_type', models.CharField(max_length=255)),
                ('document_filename', models.CharField(max_length=255, null=True, blank=True)),
                ('user', models.ForeignKey(related_name='submissions', to=settings.AUTH_USER_MODEL)),
                ('workgroup', models.ForeignKey(related_name='submissions', to='edx_solutions_projects.Workgroup')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkgroupSubmissionReview',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('reviewer', models.CharField(max_length=255)),
                ('question', models.CharField(max_length=1024)),
                ('answer', models.TextField()),
                ('content_id', models.CharField(max_length=255, null=True, blank=True)),
                ('submission', models.ForeignKey(related_name='reviews', to='edx_solutions_projects.WorkgroupSubmission')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkgroupUser',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
                ('workgroup', models.ForeignKey(to='edx_solutions_projects.Workgroup')),
            ],
            options={
                'db_table': 'edx_solutions_projects_workgroup_users',
            },
        ),
        migrations.AddField(
            model_name='workgroup',
            name='users',
            field=models.ManyToManyField(related_name='workgroups', through='edx_solutions_projects.WorkgroupUser', to=settings.AUTH_USER_MODEL, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='project',
            unique_together=set([('course_id', 'content_id', 'organization')]),
        ),
    ]
