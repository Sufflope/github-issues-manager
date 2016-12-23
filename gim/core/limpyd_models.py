from datetime import datetime, timedelta
import json
from random import choice, randint

from django.db.models import get_model

from limpyd import model as lmodel, fields as lfields
from limpyd.contrib.collection import ExtendedCollectionManager
from limpyd_jobs.utils import datetime_to_score

from gim.core import get_main_limpyd_database
from gim.github import ApiError


class Token(lmodel.RedisModel):

    database = get_main_limpyd_database()
    collection_manager = ExtendedCollectionManager

    username = lfields.InstanceHashField(indexable=True)
    token = lfields.InstanceHashField(unique=True)

    rate_limit_remaining = lfields.StringField()  # expirable field
    rate_limit_limit = lfields.InstanceHashField()  # how much by hour
    rate_limit_reset = lfields.InstanceHashField()  # same as ttl(rate_limit_remaining)
    rate_limit_score = lfields.InstanceHashField()  # based on remaining and reset, the higher, the better
    scopes = lfields.SetField(indexable=True)  # list of scopes for this token
    valid_scopes = lfields.InstanceHashField(indexable=True)  # if scopes are valid
    available = lfields.InstanceHashField(indexable=True)  # if the token is publicly available
    last_call = lfields.InstanceHashField()  # last github call, even if error
    last_call_ok = lfields.InstanceHashField()  # last github call that was not an error
    last_call_ko = lfields.InstanceHashField()  # last github call that was an error
    errors = lfields.SortedSetField()  # will store all errors
    unavailabilities = lfields.SortedSetField()  # will store all queries that set the token as unavailable
    can_access_graphql_api = lfields.InstanceHashField(indexable=True)  # if the user can access the githup graphql api
    graphql_rate_limit_remaining = lfields.StringField()  # expirable field
    graphql_rate_limit_limit = lfields.InstanceHashField()  # how much by hour
    graphql_rate_limit_reset = lfields.InstanceHashField()  # same as ttl(graphql_rate_limit_remaining)
    graphql_rate_limit_score = lfields.InstanceHashField()  # based on remaining and reset, the higher, the better
    graphql_available = lfields.InstanceHashField(indexable=True)  # if the token is publicly available

    repos_admin = lfields.SetField(indexable=True)
    repos_push = lfields.SetField(indexable=True)
    repos_pull = lfields.SetField(indexable=True)

    # keep some to do post actions by users
    MAX_EXPECTED = 5000
    LIMIT = 500
    GRAPHQL_MAX_EXPECTED = 200
    GRAPHQL_LIMIT = 50

    @property
    def user(self):
        if not hasattr(self, '_user'):
            from gim.core.models import GithubUser
            self._user = GithubUser.objects.get(username=self.username.hget())
        return self._user

    @classmethod
    def update_tokens_from_gh(cls, gh, *args, **kwargs):
        access_token = gh._connection_args.get('access_token')
        if not access_token:
            return
        try:
            username = Token.collection(token=access_token).instances()[0].username.hget()
        except IndexError:
            return
        tokens = Token.collection(username=username).instances()
        for token in tokens:
            token.update_from_gh(gh, *args, **kwargs)

    def update_from_gh(self, gh, api_error, method, path, request_headers, response_headers, kw):
        """
        Will update the current token object with information from the gh object
        and the error, if not None:
        - will save current date, and one if error or not
        - save the rate_limit limit and remaining, expiring the remaining with
          the reset givent by github
        - save scopes and mark is valid or notes
        - save the api_error if given
        If the remaining call is small (< 10% of the limit), mark the token as
        unavailable and ask for a reset when they will be available
        """
        username = gh._connection_args.get('username')
        if username:
            self.username.hset(username)

        is_graphql = path == '/graphql'

        if is_graphql:
            rate_limit_remaining_field = self.graphql_rate_limit_remaining
            rate_limit_limit_field = self.graphql_rate_limit_limit
            rate_limit_reset_field = self.graphql_rate_limit_reset
            available_field = self.graphql_available
            default_limit = self.GRAPHQL_LIMIT
            max_expected = self.GRAPHQL_MAX_EXPECTED
        else:
            rate_limit_remaining_field = self.rate_limit_remaining
            rate_limit_limit_field = self.rate_limit_limit
            rate_limit_reset_field = self.rate_limit_reset
            available_field = self.available
            default_limit = self.LIMIT
            max_expected = self.MAX_EXPECTED

        # save last calls
        now = datetime.utcnow()
        str_now = str(now)
        self.last_call.hset(str_now)

        log_unavailability = False

        is_error = False
        if api_error:
            is_error = True
            if hasattr(api_error, 'code'):
                if api_error.code == 304 or (200 <= api_error.code < 300):
                    is_error = False

        if not is_error:
            self.last_call_ok.hset(str_now)
        else:
            self.last_call_ko.hset(str_now)

        # reset scopes (only if we have the header)
        if gh.x_oauth_scopes is not None:
            self.scopes.delete()
            if gh.x_oauth_scopes:
                self.scopes.sadd(*gh.x_oauth_scopes)
            self.valid_scopes.hset(int(bool(gh.x_oauth_scopes)))
            if not gh.x_oauth_scopes or 'repo' not in gh.x_oauth_scopes:
                available_field.hset(0)
                log_unavailability = True
                self.ask_for_reset_flags(3600, is_graphql)  # check again in an hour

        if gh.x_ratelimit_remaining != -1:
            # add rate limit remaining, clear it after reset time
            rate_limit_remaining_field.set(gh.x_ratelimit_remaining)
            if gh.x_ratelimit_reset != -1:
                self.connection.expireat(rate_limit_remaining_field.key, gh.x_ratelimit_reset)
                rate_limit_reset_field.hset(gh.x_ratelimit_reset)
            else:
                self.connection.expire(rate_limit_remaining_field.key, 3600)
                rate_limit_reset_field.hset(datetime_to_score(datetime.utcnow()+timedelta(seconds=3600)))

            # if to few requests remaining, consider it as not available for public queries
            limit = max_expected if gh.x_ratelimit_limit == -1 else gh.x_ratelimit_limit
            rate_limit_limit_field.hset(limit)
            if not gh.x_ratelimit_remaining or gh.x_ratelimit_remaining < default_limit:
                available_field.hset(0)
                log_unavailability = True
                self.ask_for_reset_flags(None, is_graphql)
            else:
                available_field.hset(1)

        self.set_compute_score(is_graphql)

        # ask for a flag every 50 calls, to be sure to have one
        if not (gh.x_ratelimit_remaining+1 or max_expected) % 50:
            self.ask_for_reset_flags(None, is_graphql)

        if is_error or log_unavailability:
            json_data = {
                'request': {
                    'path': path,
                    'method': method,
                    'headers': request_headers,
                    'args': kw,
                },
                'response': {
                    'headers': response_headers,
                },
            }
            if api_error:
                if hasattr(api_error, 'code'):
                    json_data['response']['code'] = api_error.code
                if api_error.response and api_error.response.json:
                    json_data['response']['content'] = api_error.response.json

            json_data = json.dumps(json_data)
            when = datetime_to_score(now)

            if is_error:
                self.errors.zadd(when, json_data)
            if log_unavailability:
                self.unavailabilities.zadd(when, json_data)

    def reset_flags(self, for_graphql=False):
        """
        Will reset the flags of this token (actually only "available")
        If the token object is not in a good state to be reset, a task to reset
        it later will be asked.
        Return False if the reset was not successful and need to be done later
        """

        if for_graphql:
            rate_limit_remaining_field = self.graphql_rate_limit_remaining
            rate_limit_limit_field = self.graphql_rate_limit_limit
            rate_limit_reset_field = self.graphql_rate_limit_reset
            available_field = self.graphql_available
            max_expected = self.GRAPHQL_MAX_EXPECTED
        else:
            rate_limit_remaining_field = self.rate_limit_remaining
            rate_limit_limit_field = self.rate_limit_limit
            rate_limit_reset_field = self.rate_limit_reset
            available_field = self.available
            max_expected = self.MAX_EXPECTED

        # not expired yet, ask to reset flags later
        if self.connection.exists(rate_limit_remaining_field.key):
            return False

        rate_limit_reset_field.hset(0)
        # set the remaining to the max to let this token be fetched first when
        # sorting by rate_limit_remaining
        rate_limit_remaining_field.set(rate_limit_limit_field.hget() or max_expected)

        self.set_compute_score(for_graphql)

        # set the token available again only if it has valid scopes
        if self.valid_scopes.hget() == '1':
            available_field.hset(1)

        return True

    def set_compute_score(self, for_graphql=False):
        if for_graphql:
            rate_limit_remaining_field = self.graphql_rate_limit_remaining
            rate_limit_score_field = self.graphql_rate_limit_score
            default_limit = self.GRAPHQL_LIMIT
        else:
            rate_limit_remaining_field = self.rate_limit_remaining
            rate_limit_score_field = self.rate_limit_score
            default_limit = self.LIMIT

        remaining_calls = int(rate_limit_remaining_field.get() or 0)
        remaining_seconds = self.get_remaining_seconds(for_graphql) or -2
        score = (remaining_calls - default_limit) / float(remaining_seconds)
        rate_limit_score_field.hset(score)

    def get_remaining_seconds(self, for_graphql=False):
        """
        Return the time before the reset of the rate limiting
        """
        field = self.graphql_rate_limit_remaining if for_graphql else self.rate_limit_remaining
        return self.connection.ttl(field.key)

    def ask_for_reset_flags(self, delayed_for=None, for_graphql=False):
        """
        Create a task to reset the token's flags later. But if the token is in
        a good state, reset them now instead of creating a flag
        """
        if not delayed_for:
            ttl = self.get_remaining_seconds(for_graphql)
            if ttl <= 0:
                field = self.graphql_rate_limit_remaining if for_graphql else self.rate_limit_remaining
                field.delete()
                self.reset_flags(for_graphql)
                return
            delayed_for = ttl + 2

        from gim.core.tasks.tokens import ResetTokenFlags
        job_key = self.token.hget()
        if for_graphql:
            job_key += ':graphql'
        ResetTokenFlags.add_job(job_key, delayed_for=delayed_for)

    @classmethod
    def update_repos_for_user(cls, user):
        """
        Update the repos_admin and repo_push fields with pks of repositories
        the user can admin/push/pull, for all its tokens
        """
        repos_admin = user.get_repos_pks_with_permissions('admin')
        repos_push = user.get_repos_pks_with_permissions('admin', 'push')
        repos_pull = user.get_repos_pks_with_permissions('admin', 'push', 'pull')

        for token in cls.collection(username=user.username).instances():
            token.repos_admin.delete()
            if repos_admin:
                token.repos_admin.sadd(*repos_admin)

            token.repos_push.delete()
            if repos_push:
                token.repos_push.sadd(*repos_push)

            token.repos_pull.delete()
            if repos_pull:
                token.repos_pull.sadd(*repos_pull)

    @classmethod
    def get_one_for_repository(cls, repository_pk, permission, available=True, sort_by='-rate_limit_score', for_graphql=False):
        collection = cls.collection(valid_scopes=1)
        if available:
            if for_graphql:
                collection = collection.filter(graphql_available=1)
            else:
                collection = collection.filter(available=1)
        if for_graphql:
            collection = collection.filter(can_access_graphql_api=1)
            if sort_by:
                if sort_by.startswith('rate_limit'):
                    sort_by = 'graphql_' + sort_by
                elif sort_by.startswith('-rate_limit'):
                    sort_by = '-graphql_' + sort_by[1:]
        if permission == 'admin':
            collection.filter(repos_admin=repository_pk)
        elif permission == 'push':
            collection.filter(repos_push=repository_pk)
        elif permission == 'pull':
            collection.filter(repos_pull=repository_pk)
        try:
            if sort_by is None:
                token = choice(collection.instances())
            else:
                token = collection.sort(by=sort_by).instances()[0]
        except IndexError:
            return None
        else:
            return token

    @classmethod
    def ensure_graphql_gh_for_repository(cls, gh, repository_pk, permission, min_remaining=None):
        if min_remaining is None:
            min_remaining = cls.GRAPHQL_LIMIT

        token = cls.get_for_gh(gh)

        if token.can_access_graphql_api.hget() == '1':
            try:
                remaining = int(token.graphql_rate_limit_remaining.get())
            except:
                remaining = cls.GRAPHQL_MAX_EXPECTED

            if remaining > min_remaining:
                return gh

        token = cls.get_one_for_repository(repository_pk, permission, for_graphql=True)

        if not token:
            return None

        try:
            remaining = int(token.graphql_rate_limit_remaining.get())
        except:
            remaining = cls.GRAPHQL_MAX_EXPECTED

        if remaining <= min_remaining:
            return None

        return token.gh

    @classmethod
    def get_one(cls, available=True, sort_by='-rate_limit_score', for_graphql=False):
        collection = cls.collection(valid_scopes=1)
        if available:
            if for_graphql:
                collection = collection.filter(graphql_available=1)
            else:
                collection = collection.filter(available=1)
        if for_graphql:
            collection = collection.filter(can_access_graphql_api=1)
            if sort_by:
                if sort_by.startswith('rate_limit'):
                    sort_by = 'graphql_' + sort_by
                elif sort_by.startswith('-rate_limit'):
                    sort_by = '-graphql_' + sort_by[1:]
        try:
            if sort_by is None:
                token = choice(collection.instances())
            else:
                token = collection.sort(by=sort_by).instances()[0]
        except IndexError:
            return None
        else:
            return token

    @classmethod
    def get_one_for_username(cls, username, available=True, sort_by='-rate_limit_score', for_graphql=False):
        collection = cls.collection(username=username, valid_scopes=1)
        if available:
            if for_graphql:
                collection = collection.filter(graphql_available=1)
            else:
                collection = collection.filter(available=1)
        if for_graphql:
            collection = collection.filter(can_access_graphql_api=1)
            if sort_by:
                if sort_by.startswith('rate_limit'):
                    sort_by = 'graphql_' + sort_by
                elif sort_by.startswith('-rate_limit'):
                    sort_by = '-graphql_' + sort_by[1:]
        try:
            if sort_by is None:
                token = choice(collection.instances())
            else:
                token = collection.sort(by=sort_by).instances()[0]
        except IndexError:
            return None
        else:
            return token

    @property
    def gh(self):
        from .ghpool import Connection
        username, token = self.hmget('username', 'token')
        return Connection.get(username=username, access_token=token)

    @classmethod
    def get_for_gh(cls, gh):
        return cls.get(token=gh._connection_args['access_token'])

    def check_graphql_access(self):
        # only fetch for users already having graphql activated if the token was not used recently
        if self.can_access_graphql_api.hget() == '1':
            if (self.get_remaining_seconds(True) or 0) > 0:
                return
        # for users not having access, fetch randomly (Called once per 5mn, random 1/6 => once per 30mn in average)
        else:
            if randint(0, 5):
                return

        try:
            self.gh.graphql.post(query="query{ viewer { login }}")
        except ApiError:
            self.can_access_graphql_api.hset(0)
            return False
        else:
            self.can_access_graphql_api.hset(1)
            return True

    @classmethod
    def check_graphql_accesses(cls):
        for token in cls.collection().instances():
            token.check_graphql_access()


class DeletedInstance(lmodel.RedisModel):
    """Keep a reference to each instance of GithubObjectWithId that where dist-deleted

    We need this to avoid retrieving back from Github the deleted elements, for example
    if a list of elements was fetched at the same time of the delete, we may have the
    element back.
    So we'll use this model to store them and ignore them from Github.

    """

    database = get_main_limpyd_database()
    collection_manager = ExtendedCollectionManager

    ident = lfields.InstanceHashField(indexable=True, unique=True)
    timestamp = lfields.InstanceHashField(indexable=True)

    @staticmethod
    def get_ident_for_model_and_id(model, github_id):
        return '%s.%s.%s' % (
            model._meta.app_label,
            model._meta.model_name,
            github_id,
        )

    @classmethod
    def get_for_model_and_id(cls, model, github_id):
        return cls.get(ident=cls.get_ident_for_model_and_id(model, github_id))

    @classmethod
    def get_for_instance(cls, instance):
        return cls.get_for_model_and_id(instance.__class__, instance.github_id)

    @classmethod
    def exist_for_model_and_id(cls, model, github_id):
        return cls.exists(ident=cls.get_ident_for_model_and_id(model, github_id))

    @classmethod
    def exist_for_instance(cls, instance):
        return cls.exist_for_model_and_id(instance.__class__, instance.github_id)

    @classmethod
    def create_for_model_and_id(cls, model, github_id):
        instance, created = cls.get_or_connect(ident=cls.get_ident_for_model_and_id(model, github_id))
        if created:
            instance.timestamp.hset(datetime_to_score(datetime.utcnow()))
        return instance

    @classmethod
    def create_for_instance(cls, instance):
        return cls.create_for_model_and_id(instance.__class__, instance.github_id)

    @classmethod
    def clear_old(cls, older_than_seconds=3600):
        """Remove the entries that are older than the given number of seconds"""

        min_timestamp = datetime_to_score(datetime.utcnow()) - older_than_seconds

        to_delete = []
        count = 0
        for instance in cls.collection().instances():
            count += 1
            timestamp = instance.timestamp.hget()
            try:
                timestamp = float(timestamp)
            except ValueError:
                to_delete.append(instance)
                continue

            if timestamp < min_timestamp:
                to_delete.append(instance)

        for instance in to_delete:
            instance.delete()

        print('Deleted %s "deleted instances" on %s.' % (len(to_delete), count))

    def get_instance(self):
        app_label, model_name, github_id = self.ident.hget().split('.')
        try:
            model = get_model(app_label, model_name)
        except Exception:
            return None
        try:
            return model.objects.get(github_id=github_id)
        except model.DoesNotExist:
            return None

    @classmethod
    def manage_undeleted(cls):
        """Delete all instances existing in the database that should not"""

        count_total = 0
        count_deleted = 0

        for limpyd_instance in cls.collection().instances():
            count_total += 1
            instance = limpyd_instance.get_instance()
            if instance:
                count_deleted +=1
                instance.delete()

        print('Deleted %s instances on %s.' % (count_deleted, count_total))
