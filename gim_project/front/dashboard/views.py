from django.views.generic import ListView, TemplateView
from django.core.urlresolvers import reverse_lazy

from activity.limpyd_models import RepositoryActivity
from ..views import SubscribedRepositoriesMixin, DeferrableViewPart
from subscriptions.models import SUBSCRIPTION_STATES


class DashboardActivityPart(DeferrableViewPart, SubscribedRepositoriesMixin, TemplateView):
    part_url = reverse_lazy('front:dashboard:activity')
    template_name = 'front//dashboard/include_activity.html'
    deferred_template_name = 'front/dashboard/include_activity_deferred.html'

    repository_pks = None

    def inherit_from_view(self, view):
        super(DashboardActivityPart, self).inherit_from_view(view)
        self.repository_pks = view.repository_pks

    def get_pks(self):
        return [s.repository_id for s in self.subscriptions]

    def get_context_data(self, *args, **kwargs):
        context = super(DashboardActivityPart, self).get_context_data(**kwargs)

        activity = RepositoryActivity.get_for_repositories(
                            pks=self.repository_pks or self.get_pks(),
                            start=0,
                            stop=49
                        )
        context['activity'] = RepositoryActivity.load_objects(activity)

        return context


class DashboardHome(SubscribedRepositoriesMixin, ListView):
    template_name = 'front/dashboard/home.html'
    url_name = 'front:dashboard:home'

    def get_context_data(self, **kwargs):
        context = super(DashboardHome, self).get_context_data(**kwargs)

        repositories = context['subscribed_repositories']
        subscription_by_repo_id = dict((s.repository_id, s) for s in self.subscriptions)

        total_counts = {
            'assigned': 0,
            'created': 0,
            'prs': 0,
            'all_prs': 0,
            'all': 0,
        }

        for repository in repositories:
            issues = repository.issues.ready().filter(state='open')

            repository.user_counts_open = {
                'all': issues.count(),
            }

            # count prs only if we have issues (no issues = no prs)
            if repository.user_counts_open['all']:
                repository.user_counts_open['all_prs'] = issues.filter(
                                                is_pull_request=True).count()
            else:
                repository.user_counts_open['all_prs'] = 0

            repository.user_counts_open['created'] = issues.filter(
                                                user=self.request.user).count()

            # # count prs only if we have issues (no issues = no prs)
            # if repository.user_counts_open['created']:
            #     repository.user_counts_open['prs'] = issues.filter(
            #             is_pull_request=True, user=self.request.user).count()
            # else:
            #     repository.user_counts_open['prs'] = 0

            # count assigned only if owner or collaborator
            subscription = subscription_by_repo_id.get(repository.id, None)
            if subscription and subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
                repository.user_counts_open['assigned'] = issues.filter(
                                            assignee=self.request.user).count()

            for key, count in repository.user_counts_open.items():
                total_counts[key] += count

        context['total_counts'] = total_counts

        context['subscription_by_repo_id'] = subscription_by_repo_id

        self.repository_pks = subscription_by_repo_id.keys()
        context['parts'] = {
            'activity': DashboardActivityPart().get_as_deferred(self),
        }

        return context
