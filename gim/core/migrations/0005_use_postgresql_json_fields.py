# -*- coding: utf-8 -*-
# Generated by Django 1.9.12 on 2016-12-29 13:06
from __future__ import unicode_literals

from django.db import migrations
import gim.core.utils


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_django19_updates_on_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commitfile',
            name='hunk_shas',
            field=gim.core.utils.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='labeltype',
            name='edit_details',
            field=gim.core.utils.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='pullrequestfile',
            name='hunk_shas',
            field=gim.core.utils.JSONField(blank=True, null=True),
        ),
    ]
