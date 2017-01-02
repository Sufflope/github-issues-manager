# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import jsonfield.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(db_index=True)),
                ('title', models.TextField()),
                ('is_update', models.BooleanField(default=False)),
                ('related_object_id', models.PositiveIntegerField(db_index=True, null=True, blank=True)),
                ('issue', models.ForeignKey(to='core.Issue')),
                ('related_content_type', models.ForeignKey(blank=True, to='contenttypes.ContentType', null=True)),
                ('repository', models.ForeignKey(to='core.Repository')),
            ],
            options={
                'ordering': ('created_at',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EventPart',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('field', models.CharField(max_length=50, db_index=True)),
                ('old_value', jsonfield.fields.JSONField(null=True, blank=True)),
                ('new_value', jsonfield.fields.JSONField(null=True, blank=True)),
                ('event', models.ForeignKey(related_name='parts', to='events.Event')),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
    ]
