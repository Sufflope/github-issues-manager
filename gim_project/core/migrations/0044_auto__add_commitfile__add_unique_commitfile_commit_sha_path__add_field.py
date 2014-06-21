# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Removing unique constraint on 'PullRequestFile', fields ['tree', 'sha', 'path']
        db.delete_unique(u'core_pullrequestfile', ['tree', 'sha', 'path'])

        # Adding model 'CommitFile'
        db.create_table(u'core_commitfile', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('fetched_at', self.gf('django.db.models.fields.DateTimeField')(null=True, blank=True)),
            ('github_status', self.gf('django.db.models.fields.PositiveSmallIntegerField')(default=1, db_index=True)),
            ('path', self.gf('django.db.models.fields.TextField')(db_index=True, null=True, blank=True)),
            ('status', self.gf('django.db.models.fields.CharField')(max_length=32, null=True, blank=True)),
            ('nb_additions', self.gf('django.db.models.fields.PositiveIntegerField')(null=True, blank=True)),
            ('nb_deletions', self.gf('django.db.models.fields.PositiveIntegerField')(null=True, blank=True)),
            ('patch', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('sha', self.gf('django.db.models.fields.CharField')(max_length=40, null=True, blank=True)),
            ('repository', self.gf('django.db.models.fields.related.ForeignKey')(related_name='commit_files', to=orm['core.Repository'])),
            ('commit', self.gf('django.db.models.fields.related.ForeignKey')(related_name='files', to=orm['core.Commit'])),
        ))
        db.send_create_signal('core', ['CommitFile'])

        # Adding unique constraint on 'CommitFile', fields ['commit', 'sha', 'path']
        db.create_unique(u'core_commitfile', ['commit_id', 'sha', 'path'])

        # Adding field 'Commit.files_fetched_at'
        db.add_column(u'core_commit', 'files_fetched_at',
                      self.gf('django.db.models.fields.DateTimeField')(null=True, blank=True),
                      keep_default=False)

        # Adding field 'Commit.nb_additions'
        db.add_column(u'core_commit', 'nb_additions',
                      self.gf('django.db.models.fields.PositiveIntegerField')(null=True, blank=True),
                      keep_default=False)

        # Adding field 'Commit.nb_deletions'
        db.add_column(u'core_commit', 'nb_deletions',
                      self.gf('django.db.models.fields.PositiveIntegerField')(null=True, blank=True),
                      keep_default=False)

        # Deleting field 'PullRequestFile.nb_changes'
        db.delete_column(u'core_pullrequestfile', 'nb_changes')

        # Adding unique constraint on 'PullRequestFile', fields ['repository', 'tree', 'sha', 'path']
        db.create_unique(u'core_pullrequestfile', ['repository_id', 'tree', 'sha', 'path'])


    def backwards(self, orm):
        # Removing unique constraint on 'PullRequestFile', fields ['repository', 'tree', 'sha', 'path']
        db.delete_unique(u'core_pullrequestfile', ['repository_id', 'tree', 'sha', 'path'])

        # Removing unique constraint on 'CommitFile', fields ['commit', 'sha', 'path']
        db.delete_unique(u'core_commitfile', ['commit_id', 'sha', 'path'])

        # Deleting model 'CommitFile'
        db.delete_table(u'core_commitfile')

        # Deleting field 'Commit.files_fetched_at'
        db.delete_column(u'core_commit', 'files_fetched_at')

        # Deleting field 'Commit.nb_additions'
        db.delete_column(u'core_commit', 'nb_additions')

        # Deleting field 'Commit.nb_deletions'
        db.delete_column(u'core_commit', 'nb_deletions')

        # Adding field 'PullRequestFile.nb_changes'
        db.add_column(u'core_pullrequestfile', 'nb_changes',
                      self.gf('django.db.models.fields.PositiveIntegerField')(null=True, blank=True),
                      keep_default=False)

        # Adding unique constraint on 'PullRequestFile', fields ['tree', 'sha', 'path']
        db.create_unique(u'core_pullrequestfile', ['tree', 'sha', 'path'])


    models = {
        u'auth.group': {
            'Meta': {'object_name': 'Group'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'auth.permission': {
            'Meta': {'ordering': "(u'content_type__app_label', u'content_type__model', u'codename')", 'unique_together': "((u'content_type', u'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'core.availablerepository': {
            'Meta': {'ordering': "('organization_username', 'repository')", 'unique_together': "(('user', 'repository'),)", 'object_name': 'AvailableRepository'},
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'organization_id': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'organization_username': ('django.db.models.fields.CharField', [], {'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'permission': ('django.db.models.fields.CharField', [], {'max_length': '5'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['core.Repository']"}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'available_repositories_set'", 'to': "orm['core.GithubUser']"})
        },
        'core.commit': {
            'Meta': {'ordering': "('committed_at',)", 'unique_together': "(('repository', 'sha'),)", 'object_name': 'Commit'},
            'author': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'commits_authored'", 'null': 'True', 'to': "orm['core.GithubUser']"}),
            'author_email': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'author_name': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'authored_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'comments_count': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'committed_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'committer': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'commits_commited'", 'null': 'True', 'to': "orm['core.GithubUser']"}),
            'committer_email': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'committer_name': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'deleted': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'files_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'message': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'nb_additions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'nb_deletions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commits'", 'to': "orm['core.Repository']"}),
            'sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'tree': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'})
        },
        'core.commitcomment': {
            'Meta': {'ordering': "('created_at',)", 'object_name': 'CommitComment'},
            'body': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'body_html': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'commit': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commit_comments'", 'null': 'True', 'to': "orm['core.Commit']"}),
            'commit_sha': ('django.db.models.fields.CharField', [], {'max_length': '40'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'entry_point': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'comments'", 'to': "orm['core.CommitCommentEntryPoint']"}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'linked_commits': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['core.Commit']", 'symmetrical': 'False'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commit_comments'", 'to': "orm['core.Repository']"}),
            'updated_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commit_comments'", 'to': "orm['core.GithubUser']"})
        },
        'core.commitcommententrypoint': {
            'Meta': {'ordering': "('created_at',)", 'unique_together': "(('repository', 'commit_sha', 'path', 'position'),)", 'object_name': 'CommitCommentEntryPoint'},
            'commit': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commit_comments_entry_point'", 'null': 'True', 'to': "orm['core.Commit']"}),
            'commit_sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'diff_hunk': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'path': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'position': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commit_comments_entry_points'", 'to': "orm['core.Repository']"}),
            'updated_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'commit_comments_entry_points'", 'null': 'True', 'to': "orm['core.GithubUser']"})
        },
        'core.commitfile': {
            'Meta': {'ordering': "('path',)", 'unique_together': "(('commit', 'sha', 'path'),)", 'object_name': 'CommitFile'},
            'commit': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'files'", 'to': "orm['core.Commit']"}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'nb_additions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'nb_deletions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'patch': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'path': ('django.db.models.fields.TextField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'commit_files'", 'to': "orm['core.Repository']"}),
            'sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'}),
            'status': ('django.db.models.fields.CharField', [], {'max_length': '32', 'null': 'True', 'blank': 'True'})
        },
        'core.githubuser': {
            'Meta': {'ordering': "('username',)", 'object_name': 'GithubUser'},
            'available_repositories': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['core.Repository']", 'through': "orm['core.AvailableRepository']", 'symmetrical': 'False'}),
            'avatar_url': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Group']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_organization': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'organizations': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'organizations_rel_+'", 'to': "orm['core.GithubUser']"}),
            'organizations_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'organizations_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'starred_repositories': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'starred'", 'symmetrical': 'False', 'to': "orm['core.Repository']"}),
            'teams': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'members'", 'symmetrical': 'False', 'to': "orm['core.Team']"}),
            'teams_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'teams_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'token': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Permission']"}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '255'}),
            'watched_repositories': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'watched'", 'symmetrical': 'False', 'to': "orm['core.Repository']"})
        },
        'core.issue': {
            'Meta': {'unique_together': "(('repository', 'number'),)", 'object_name': 'Issue'},
            'assignee': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'assigned_issues'", 'null': 'True', 'to': "orm['core.GithubUser']"}),
            'base_label': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'base_sha': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'body': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'body_html': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'closed_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'closed_by': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'closed_issues'", 'null': 'True', 'to': "orm['core.GithubUser']"}),
            'closed_by_fetched': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'comments_count': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'comments_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'comments_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'commits': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'issues'", 'symmetrical': 'False', 'through': "orm['core.IssueCommits']", 'to': "orm['core.Commit']"}),
            'commits_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'commits_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'events_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'events_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'files_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'files_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_pr_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            'head_label': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'head_sha': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_pull_request': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'labels': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'issues'", 'symmetrical': 'False', 'to': "orm['core.Label']"}),
            'mergeable': ('django.db.models.fields.NullBooleanField', [], {'null': 'True', 'blank': 'True'}),
            'mergeable_state': ('django.db.models.fields.CharField', [], {'max_length': '20', 'null': 'True', 'blank': 'True'}),
            'merged': ('django.db.models.fields.NullBooleanField', [], {'null': 'True', 'blank': 'True'}),
            'merged_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'merged_by': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'merged_prs'", 'null': 'True', 'to': "orm['core.GithubUser']"}),
            'milestone': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'issues'", 'null': 'True', 'to': "orm['core.Milestone']"}),
            'nb_additions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'nb_changed_files': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'nb_commits': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'nb_deletions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'number': ('django.db.models.fields.PositiveIntegerField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'pr_comments_count': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'pr_comments_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'pr_comments_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'pr_fetched_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'issues'", 'to': "orm['core.Repository']"}),
            'state': ('django.db.models.fields.CharField', [], {'max_length': '10', 'db_index': 'True'}),
            'title': ('django.db.models.fields.TextField', [], {'db_index': 'True'}),
            'updated_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'created_issues'", 'to': "orm['core.GithubUser']"})
        },
        'core.issuecomment': {
            'Meta': {'ordering': "('created_at',)", 'object_name': 'IssueComment'},
            'body': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'body_html': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issue': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'comments'", 'to': "orm['core.Issue']"}),
            'linked_commits': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['core.Commit']", 'symmetrical': 'False'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'comments'", 'to': "orm['core.Repository']"}),
            'updated_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'issue_comments'", 'to': "orm['core.GithubUser']"})
        },
        'core.issuecommits': {
            'Meta': {'object_name': 'IssueCommits'},
            'commit': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'related_commits'", 'to': "orm['core.Commit']"}),
            'deleted': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issue': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'related_commits'", 'to': "orm['core.Issue']"})
        },
        'core.issueevent': {
            'Meta': {'ordering': "('created_at', 'github_id')", 'object_name': 'IssueEvent'},
            'commit_sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'event': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issue': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'events'", 'to': "orm['core.Issue']"}),
            'related_content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']", 'null': 'True', 'blank': 'True'}),
            'related_object_id': ('django.db.models.fields.PositiveIntegerField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'issues_events'", 'to': "orm['core.Repository']"}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'issues_events'", 'null': 'True', 'to': "orm['core.GithubUser']"})
        },
        'core.label': {
            'Meta': {'ordering': "('label_type', 'order', 'lower_typed_name', 'lower_name')", 'unique_together': "(('repository', 'name'),)", 'object_name': 'Label', 'index_together': "(('repository', 'label_type', 'order'),)"},
            'api_url': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'color': ('django.db.models.fields.CharField', [], {'max_length': '6'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'label_type': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'labels'", 'null': 'True', 'on_delete': 'models.SET_NULL', 'to': "orm['core.LabelType']"}),
            'lower_name': ('django.db.models.fields.TextField', [], {'db_index': 'True'}),
            'lower_typed_name': ('django.db.models.fields.TextField', [], {'db_index': 'True'}),
            'name': ('django.db.models.fields.TextField', [], {}),
            'order': ('django.db.models.fields.IntegerField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'labels'", 'to': "orm['core.Repository']"}),
            'typed_name': ('django.db.models.fields.TextField', [], {'db_index': 'True'})
        },
        'core.labeltype': {
            'Meta': {'ordering': "('lower_name',)", 'object_name': 'LabelType'},
            'edit_details': ('jsonfield.fields.JSONField', [], {'null': 'True', 'blank': 'True'}),
            'edit_mode': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'lower_name': ('django.db.models.fields.CharField', [], {'max_length': '250', 'db_index': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '250'}),
            'regex': ('django.db.models.fields.TextField', [], {}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'label_types'", 'to': "orm['core.Repository']"})
        },
        'core.milestone': {
            'Meta': {'ordering': "('-number',)", 'object_name': 'Milestone'},
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'creator': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'milestones'", 'to': "orm['core.GithubUser']"}),
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'due_on': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'number': ('django.db.models.fields.PositiveIntegerField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'milestones'", 'to': "orm['core.Repository']"}),
            'state': ('django.db.models.fields.CharField', [], {'max_length': '10', 'db_index': 'True'}),
            'title': ('django.db.models.fields.TextField', [], {'db_index': 'True'})
        },
        'core.pullrequestcomment': {
            'Meta': {'ordering': "('created_at',)", 'object_name': 'PullRequestComment'},
            'body': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'body_html': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'entry_point': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'comments'", 'to': "orm['core.PullRequestCommentEntryPoint']"}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issue': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'pr_comments'", 'to': "orm['core.Issue']"}),
            'linked_commits': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['core.Commit']", 'symmetrical': 'False'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'pr_comments'", 'to': "orm['core.Repository']"}),
            'updated_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'pr_comments'", 'to': "orm['core.GithubUser']"})
        },
        'core.pullrequestcommententrypoint': {
            'Meta': {'ordering': "('created_at',)", 'unique_together': "(('issue', 'original_commit_sha', 'path', 'original_position'),)", 'object_name': 'PullRequestCommentEntryPoint'},
            'commit_sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'diff_hunk': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issue': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'pr_comments_entry_points'", 'to': "orm['core.Issue']"}),
            'original_commit_sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'}),
            'original_position': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'path': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'position': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'pr_comments_entry_points'", 'to': "orm['core.Repository']"}),
            'updated_at': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'pr_comments_entry_points'", 'null': 'True', 'to': "orm['core.GithubUser']"})
        },
        'core.pullrequestfile': {
            'Meta': {'ordering': "('path',)", 'unique_together': "(('repository', 'tree', 'sha', 'path'),)", 'object_name': 'PullRequestFile'},
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issue': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'files'", 'to': "orm['core.Issue']"}),
            'nb_additions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'nb_deletions': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'patch': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'path': ('django.db.models.fields.TextField', [], {'db_index': 'True', 'null': 'True', 'blank': 'True'}),
            'repository': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'pr_files'", 'to': "orm['core.Repository']"}),
            'sha': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'}),
            'status': ('django.db.models.fields.CharField', [], {'max_length': '32', 'null': 'True', 'blank': 'True'}),
            'tree': ('django.db.models.fields.CharField', [], {'max_length': '40', 'null': 'True', 'blank': 'True'})
        },
        'core.repository': {
            'Meta': {'ordering': "('owner', 'name')", 'unique_together': "(('owner', 'name'),)", 'object_name': 'Repository'},
            'collaborators': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'repositories'", 'symmetrical': 'False', 'to': "orm['core.GithubUser']"}),
            'collaborators_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'collaborators_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'comments_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'comments_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'commit_comments_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'commit_comments_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'commit_comments_last_page': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'default_branch': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'events_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'events_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'first_fetch_done': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            'has_issues': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'hook_set': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'hooks_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'hooks_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_fork': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'issues_events_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'issues_events_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'issues_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'issues_state_all_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'issues_state_closed_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'issues_state_open_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'labels_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'labels_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'milestones_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'milestones_state_closed_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'milestones_state_open_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'name': ('django.db.models.fields.TextField', [], {'db_index': 'True'}),
            'owner': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'owned_repositories'", 'to': "orm['core.GithubUser']"}),
            'pr_comments_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'pr_comments_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'private': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'prs_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'prs_state_all_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'prs_state_closed_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'prs_state_open_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'})
        },
        'core.team': {
            'Meta': {'ordering': "('name',)", 'object_name': 'Team'},
            'fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'github_id': ('django.db.models.fields.PositiveIntegerField', [], {'unique': 'True', 'null': 'True', 'blank': 'True'}),
            'github_status': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '1', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.TextField', [], {}),
            'organization': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'org_teams'", 'to': "orm['core.GithubUser']"}),
            'permission': ('django.db.models.fields.CharField', [], {'max_length': '5'}),
            'repositories': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'teams'", 'symmetrical': 'False', 'to': "orm['core.Repository']"}),
            'repositories_etag': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'repositories_fetched_at': ('django.db.models.fields.DateTimeField', [], {'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.TextField', [], {})
        }
    }

    complete_apps = ['core']