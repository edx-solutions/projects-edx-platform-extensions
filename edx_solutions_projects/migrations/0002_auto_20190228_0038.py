# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('edx_solutions_projects', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workgroupsubmission',
            name='user',
            field=models.ForeignKey(related_name='submissions', on_delete=django.db.models.deletion.DO_NOTHING, to=settings.AUTH_USER_MODEL),
        ),
    ]
