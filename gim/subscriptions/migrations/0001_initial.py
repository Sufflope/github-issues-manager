# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0002_set_notification_unread_default_to_true'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('state', models.PositiveSmallIntegerField(default=1, choices=[(1, b'Simple user'), (2, b'Collaborator'), (3, b'Admin'), (4, b'No rights')])),
                ('repository', models.ForeignKey(related_name='subscriptions', to='core.Repository')),
                ('user', models.ForeignKey(related_name='subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WaitingSubscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('repository_name', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('state', models.PositiveSmallIntegerField(default=1, choices=[(1, b'Waiting'), (2, b'Fetching'), (3, b'Adding failed')])),
                ('user', models.ForeignKey(related_name='waiting_subscriptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='waitingsubscription',
            unique_together=set([('user', 'repository_name')]),
        ),
        migrations.AlterUniqueTogether(
            name='subscription',
            unique_together=set([('user', 'repository')]),
        ),
        migrations.AlterIndexTogether(
            name='subscription',
            index_together=set([('user', 'state')]),
        ),
    ]
