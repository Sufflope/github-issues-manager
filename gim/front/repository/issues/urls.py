from django.conf.urls import patterns, url

from .views import (IssuesView, IssueView, IssueSummaryView, IssuePreviewView,
                    CreatedIssueView,
                    SimpleAjaxIssueView, FilesAjaxIssueView, CommitAjaxIssueView,
                    IssueEditState, IssueEditTitle, IssueEditBody,
                    IssueEditMilestone, IssueEditAssignee, IssueEditLabels,
                    IssueCreateView, AskFetchIssueView,
                    IssueCommentCreateView, PullRequestCommentCreateView, CommitCommentCreateView,
                    IssueCommentView, PullRequestCommentView, CommitCommentView,
                    IssueCommentEditView, PullRequestCommentEditView, CommitCommentEditView,
                    IssueCommentDeleteView, PullRequestCommentDeleteView, CommitCommentDeleteView,
                    IssuesFilterCreators, IssuesFilterAssigned, IssuesFilterClosers)

urlpatterns = patterns('',
                       url(r'^$', IssuesView.as_view(), name=IssuesView.url_name),

                       # deferrable filters
    url(r'^filter/creators/', IssuesFilterCreators.as_view(), name=IssuesFilterCreators.url_name),
                       url(r'^filter/assigned/', IssuesFilterAssigned.as_view(), name=IssuesFilterAssigned.url_name),
                       url(r'^filter/closers/', IssuesFilterClosers.as_view(), name=IssuesFilterClosers.url_name),

                       # issue view
    url(r'^(?P<issue_number>\d+)/$', IssueView.as_view(), name=IssueView.url_name),
                       url(r'^(?P<issue_number>\d+)/summary/$', IssueSummaryView.as_view(), name=IssueSummaryView.url_name),
                       url(r'^(?P<issue_number>\d+)/preview/$', IssuePreviewView.as_view(), name=IssuePreviewView.url_name),

                       # parts
    url(r'^(?P<issue_number>\d+)/files/$', FilesAjaxIssueView.as_view(), name='issue.files'),
                       url(r'^(?P<issue_number>\d+)/commits/$', SimpleAjaxIssueView.as_view(ajax_template_name='front/repository/issues/commits/include_issue_commits.html'), name='issue.commits'),
                       url(r'^(?P<issue_number>\d+)/review/$', SimpleAjaxIssueView.as_view(ajax_template_name='front/repository/issues/comments/include_pr_review.html'), name='issue.review'),
                       url(r'^(?P<issue_number>\d+)/commit/(?P<commit_sha>[a-f0-9]{40})/$', CommitAjaxIssueView.as_view(), name=CommitAjaxIssueView.url_name),

                       # edit views
    url(r'^(?P<issue_number>\d+)/edit/state/$', IssueEditState.as_view(), name=IssueEditState.url_name),
                       url(r'^(?P<issue_number>\d+)/edit/title/$', IssueEditTitle.as_view(), name=IssueEditTitle.url_name),
                       url(r'^(?P<issue_number>\d+)/edit/body/$', IssueEditBody.as_view(), name=IssueEditBody.url_name),
                       url(r'^(?P<issue_number>\d+)/edit/milestone/$', IssueEditMilestone.as_view(), name=IssueEditMilestone.url_name),
                       url(r'^(?P<issue_number>\d+)/edit/assignee/$', IssueEditAssignee.as_view(), name=IssueEditAssignee.url_name),
                       url(r'^(?P<issue_number>\d+)/edit/labels/$', IssueEditLabels.as_view(), name=IssueEditLabels.url_name),
                       url(r'^create/$', IssueCreateView.as_view(), name=IssueCreateView.url_name),
                       url(r'^created/(?P<issue_pk>\d+)/$', CreatedIssueView.as_view(), name=CreatedIssueView.url_name),
                       url(r'^ask-fetch/(?P<issue_number>\d+)/$', AskFetchIssueView.as_view(), name=AskFetchIssueView.url_name),

                       url(r'^(?P<issue_number>\d+)/comment/add/$', IssueCommentCreateView.as_view(), name=IssueCommentCreateView.url_name),
                       url(r'^(?P<issue_number>\d+)/comment/(?P<comment_pk>\d+)/$', IssueCommentView.as_view(), name=IssueCommentView.url_name),
                       url(r'^(?P<issue_number>\d+)/comment/(?P<comment_pk>\d+)/edit/$', IssueCommentEditView.as_view(), name=IssueCommentEditView.url_name),
                       url(r'^(?P<issue_number>\d+)/comment/(?P<comment_pk>\d+)/delete/$', IssueCommentDeleteView.as_view(), name=IssueCommentDeleteView.url_name),

                       url(r'^(?P<issue_number>\d+)/code-comment/add/$', PullRequestCommentCreateView.as_view(), name=PullRequestCommentCreateView.url_name),
                       url(r'^(?P<issue_number>\d+)/code-comment/(?P<comment_pk>\d+)/$', PullRequestCommentView.as_view(), name=PullRequestCommentView.url_name),
                       url(r'^(?P<issue_number>\d+)/code-comment/(?P<comment_pk>\d+)/edit/$', PullRequestCommentEditView.as_view(), name=PullRequestCommentEditView.url_name),
                       url(r'^(?P<issue_number>\d+)/code-comment/(?P<comment_pk>\d+)/delete/$', PullRequestCommentDeleteView.as_view(), name=PullRequestCommentDeleteView.url_name),

                       url(r'^(?P<issue_number>\d+)/commit/(?P<commit_sha>[a-f0-9]{40})/comment/add/$', CommitCommentCreateView.as_view(), name=CommitCommentCreateView.url_name),
                       url(r'^(?P<issue_number>\d+)/commit/(?P<commit_sha>[a-f0-9]{40})/comment/(?P<comment_pk>\d+)/$', CommitCommentView.as_view(), name=CommitCommentView.url_name),
                       url(r'^(?P<issue_number>\d+)/commit/(?P<commit_sha>[a-f0-9]{40})/comment/(?P<comment_pk>\d+)/edit/$', CommitCommentEditView.as_view(), name=CommitCommentEditView.url_name),
                       url(r'^(?P<issue_number>\d+)/commit/(?P<commit_sha>[a-f0-9]{40})/comment/(?P<comment_pk>\d+)/delete/$', CommitCommentDeleteView.as_view(), name=CommitCommentDeleteView.url_name),
                       )
