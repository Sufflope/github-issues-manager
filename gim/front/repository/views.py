import json
from collections import OrderedDict
from itertools import chain

from django.core.urlresolvers import reverse_lazy
from django.db.models import Count
from django.http import HttpResponse
from django.utils.decorators import classonlymethod
from django.utils.functional import cached_property
from django.views.generic import DetailView, UpdateView

from gim.core.diffutils import extract_hunk_header_starts, get_encoded_hunks
from gim.core.models import CommitFile, PullRequestFile

from gim.front.mixins.views import (
    DependsOnRepositoryViewMixin,
    SubscribedRepositoryViewMixin,
    WithAjaxRestrictionViewMixin,
    WithSubscribedRepositoriesViewMixin,
)


class RepositoryViewMixin(WithSubscribedRepositoriesViewMixin, SubscribedRepositoryViewMixin):

    @cached_property
    def label_types(self):
        return self.repository.label_types.annotate(
            num_labels=Count('labels')
        ).filter(
            num_labels__gt=0
        ).prefetch_related(
            'labels'
        ).order_by(
            'name'
        )

    @cached_property
    def milestones(self):
        return self.repository.milestones.all()

    @cached_property
    def projects(self):
        return self.repository.projects.annotate(
            num_columns=Count('columns')
        ).filter(
            num_columns__gt=0
        ).prefetch_related(
            'columns'
        )

    @cached_property
    def projects_including_empty(self):
        return self.repository.projects.annotate(
            num_columns=Count('columns')
        ).prefetch_related(
            'columns'
        )


class BaseRepositoryView(RepositoryViewMixin, DetailView):
    # details vue attributes
    template_name = 'front/repository/base.html'

    # specific attributes to define in subclasses
    name = None
    url_name = None
    default_qs = None

    # set to True to display in the main menu bar
    display_in_menu = False

    # internal attributes
    main_views = []

    @classonlymethod
    def as_view(cls, *args, **kwargs):
        """
        Override to call register_main_view if the view is a main one
        """
        if not getattr(cls, 'main_url_name', None):
            cls.main_url_name = cls.url_name
        if cls.display_in_menu:
            BaseRepositoryView.register_main_view(cls)
        return super(BaseRepositoryView, cls).as_view(*args, **kwargs)

    @classonlymethod
    def register_main_view(cls, view_class):
        """
        Store views to display as main views
        """
        if view_class not in BaseRepositoryView.main_views:
            BaseRepositoryView.main_views.append(view_class)

    def get_context_data(self, **kwargs):
        """
        Set default content for the repository views:
            - list of available repositories
            - list of all main views for this repository
        """
        self.object = None

        context = super(BaseRepositoryView, self).get_context_data(**kwargs)

        # we need a list of all main views for this repository
        repo_main_views = []
        reverse_kwargs = self.repository.get_reverse_kwargs()
        for view_class in BaseRepositoryView.main_views:
            main_view = {
                'url_name': view_class.url_name,
                'display_in_menu': view_class.display_in_menu,
                'url': reverse_lazy('front:repository:%s' % view_class.url_name, kwargs=reverse_kwargs),
                'qs': view_class.default_qs,
                'is_current': (self.display_in_menu or self.main_url_name != self.url_name) and self.main_url_name == view_class.url_name,
                'title': view_class.name
            }
            repo_main_views.append(main_view)

        context['can_open_issue_by_number'] = True
        context['repository_main_views'] = repo_main_views

        return context


class ToggleLocallyReviewedFileMixin(WithAjaxRestrictionViewMixin, DependsOnRepositoryViewMixin, UpdateView):
    url_base_name = '%s.toggle-locally-reviewed'
    pk_url_kwarg = 'file_pk'
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        to_set = kwargs['set_or_unset'] == 'set'
        hunk_sha = kwargs.get('hunk_sha')

        if to_set:

            self.object.mark_locally_reviewed_by_user(self.request.user, hunk_sha)
        else:
            self.object.unmark_locally_reviewed_by_user(self.request.user, hunk_sha)

        response = {
            'reviewed': self.object.is_locally_reviewed_by_user(self.request.user, hunk_sha)
        }

        if hunk_sha:
            response['file_reviewed'] = self.object.is_locally_reviewed_by_user(self.request.user)

        return HttpResponse(
            json.dumps(response),
            content_type='application/json',
        )


class ToggleLocallyReviewedCommitFile(ToggleLocallyReviewedFileMixin):
    url_name = ToggleLocallyReviewedFileMixin.url_base_name % 'commit-file'
    model = CommitFile


class ToggleLocallyReviewedPullRequestFile(ToggleLocallyReviewedFileMixin):
    url_name = ToggleLocallyReviewedFileMixin.url_base_name % 'pr-file'
    model = PullRequestFile


class ToggleLocalSplitFileMixin(WithAjaxRestrictionViewMixin, DependsOnRepositoryViewMixin, UpdateView):
    url_base_name = '%s.toggle-local-split'
    pk_url_kwarg = 'file_pk'
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        file = self.object = self.get_object()

        to_split = kwargs['split_or_unsplit'] == 'split'

        line = self.request.POST['line']

        if to_split:
            file.add_split_for_user(self.request.user, line)
        else:
            file.remove_split_for_user(self.request.user, line)

        from gim.core.diffutils import split_patch_into_hunks, split_hunks, encode_hunk

        split_lines = file.get_split_lines_for_user(self.request.user)
        hunks = split_patch_into_hunks(file.patch)

        if split_lines:
            hunks = split_hunks(hunks, split_lines)
            file.patch = '\n'.join(chain.from_iterable(hunks))
            file.hunk_shas = list(get_encoded_hunks(hunks).keys())

        file.hunks = hunks

        hunks_by_sha = OrderedDict(
            (file.hunk_shas[index], hunk)
            for index, hunk in enumerate(hunks)
        )

        locally_reviewd = file.get_hunks_locally_reviewed_by_user(self.request.user)

        response = {
            'hunks': [
                {
                    'starts': list(extract_hunk_header_starts(hunk[0])),
                    'title': hunk[0],
                    'sha': sha,
                    'locally_reviewed': locally_reviewd[sha]
                }
                for sha, hunk in hunks_by_sha.items()
            ],
        }

        return HttpResponse(
            json.dumps(response),
            content_type='application/json',
        )


class ToggleLocalSplitCommitFile(ToggleLocalSplitFileMixin):
    url_name = ToggleLocalSplitFileMixin.url_base_name % 'commit-file'
    model = CommitFile


class ToggleLocalSplitPullRequestFile(ToggleLocalSplitFileMixin):
    url_name = ToggleLocalSplitFileMixin.url_base_name % 'pr-file'
    model = PullRequestFile
