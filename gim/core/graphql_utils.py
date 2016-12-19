import base64
import json
import logging
import re

from extended_choices import Choices

from gim.github import ApiError, JsonObject

logger = logging.getLogger('gim.graphql')


GITHUB_TYPES = Choices(
    ['User', '04', 'User'],
    ['Issue', '05', 'Issue'],
    ['Commit', '06', 'Commit'],
    ['Repository', '010', 'Repository'],
    ['PullRequest', '011', 'PullRequest'],
    ['PullRequestReview', '017', 'PullRequestReview'],
    ['PullRequestReviewComment', '024', 'PullRequestReviewComment'],
)


SUBFRAGMENTS = '%(SUBFRAGMENTS)s'

FRAGMENT_PARTS = {
    'pullRequestReviews': 'reviews(first:$nbReviewsToRetrieve, after:$nextReviewsPageCursor, states:[COMMENTED,CHANGES_REQUESTED,APPROVED,DISMISSED])'
}

FRAGMENTS = {

    'pageInfoNext': ('PageInfo', """
        endCursor
        hasNextPage
    """, set()),

    'pageInfoPrevious': ('PageInfo', """
        startCursor
        hasPreviousPage
    """, set()),

    'pageInfo': ('PageInfo', SUBFRAGMENTS, {'pageInfoNext', 'pageInfoPrevious'}),

    'user': ('User', """
        idb64: id
        login
        name
        avatar_url: avatarURL
    """, set()),

    'pullRequestNumber': ('PullRequest', """
        number
    """, set()),

    'pullRequestRepository': ('PullRequest', """
        repository {
            idb64: id
        }
    """, set()),

    'pullRequestReviewBase': ('PullRequestReview', """
        idb64: id
        state
        submitted_at: submittedAt
        body
        body_html: bodyHTML
        commit {
            oid
        }
        comments(first:1) {
            totalCount
        }
    """, set()),

    'pullRequestReviewAuthor': ('PullRequestReview', """
        author {
            %(SUBFRAGMENTS)s
        }
    """, {'user'}),

    'pullRequestReviewPullRequest': ('PullRequestReview', """
        pullRequest {
            %(SUBFRAGMENTS)s
        }
    """, {'pullRequestNumber'}),

    'pullRequestReviewFull': ('PullRequestReview', SUBFRAGMENTS, {'pullRequestReviewBase', 'pullRequestReviewAuthor', 'pullRequestReviewPullRequest'}),

    'pullRequestReviewNoAuthor': ('PullRequestReview', SUBFRAGMENTS, {'pullRequestReviewBase', 'pullRequestReviewPullRequest'}),

    'pullRequestReviewNoPR': ('PullRequestReview', SUBFRAGMENTS, {'pullRequestReviewBase', 'pullRequestReviewAuthor'}),

    'pullRequestReviewsBase': ('PullRequestReviewConnection', """
        pageInfo {
            %(SUBFRAGMENTS)s
        }
    """, {'pageInfoNext'}),

    'PullRequestReviewConnectionFull': ('PullRequestReviewConnection', """
        ...pullRequestReviewsBase
        edges {
            node {
                ...pullRequestReviewNoPR
            }
        }
    """, {'pullRequestReviewsBase', 'pullRequestReviewNoPR'}),

    'PullRequestReviewConnectionNoAuthor': ('PullRequestReviewConnection', """
        ...pullRequestReviewsBase
        edges {
            node {
                ...pullRequestReviewBase
            }
        }
    """, {'pullRequestReviewsBase', 'pullRequestReviewBase'}),

    'pullRequestReviewsFull': ('PullRequest', FRAGMENT_PARTS['pullRequestReviews'] + """ {
            %(SUBFRAGMENTS)s
        }
    """, {'PullRequestReviewConnectionFull'}),
    'pullRequestReviewsNoAuthor': ('PullRequest', FRAGMENT_PARTS['pullRequestReviews'] + """ {
            %(SUBFRAGMENTS)s
        }
    """, {'PullRequestReviewConnectionNoAuthor'}),

}


def prepare_fragments():
    """Replace %(SUBFRAGMENTS)s placeholders in all fragments"""
    for name, info in FRAGMENTS.items():
        model, content, fragments = info
        include_fragments = ''
        if fragments:
            include_fragments = '\n'.join(['...%s' % fragment_name for fragment_name in fragments])
        content %= {'SUBFRAGMENTS': include_fragments}
        FRAGMENTS[name] = (model, content, fragments)

prepare_fragments()


RE_COMPLEXITY = re.compile('Query has complexity of (\d+), which exceeds max complexity of (\d+)')


class GraphQLError(ApiError):
    def __init__(self, _json, code=400):
        req = JsonObject(method='POST', url='https://api.github.com/graphql/')
        resp = JsonObject(code=code, json=_json)
        super(GraphQLError, self).__init__(req.url, req, resp)


class GraphQLComplexityError(GraphQLError):
    def __init__(self, _json, complexity, code=400):
        super(GraphQLComplexityError, self).__init__(_json, code)
        self.complexity = complexity


class GraphQLGithubInternalError(GraphQLError):
    def __init__(self, _json, code=500):
        super(GraphQLGithubInternalError, self).__init__(_json, code)


def decode_graphql_id(graphql_id):
    """GraphQL give us base64 ids in this form:
    MDE3OlB1bGxSZXF1ZXN0UmV2aWV3MjQyMzA3OA==
    Once decoded from base64, it's:
    017:PullRequestReview2423078
    The first part is an github-internal type, then we have to split the
    second part in two the get the id at the end
    """

    parts = base64.decodestring(graphql_id).split(':')
    try:
        str_id = parts[1][len(GITHUB_TYPES.for_value(parts[0]).constant):]
        try:
            return int(str_id)
        except ValueError:
            return str_id
    except KeyError:
        print('Type not registered for graphql ID %s' % ':'.join(parts))
        raise


def encode_graphql_id(github_type, github_id):
    """Do the reverse of decode_graphql_id, given a type and a github_id"""

    return base64.encodestring('%s:%s%s' % (
        github_type,
        GITHUB_TYPES.for_value(github_type).constant,
        github_id
    )).strip('\n')


def encode_graphql_id_for_object(github_based_object):
    """Helper for encode_graphql_id, using type from the object's class"""

    return encode_graphql_id(
        github_based_object.GRAPHQL_TYPE,
        getattr(github_based_object, getattr(github_based_object, 'GRAPHQL_ID_FIELD', 'github_id')),
    )


def get_all_fragments_names_for(*names):
    """Returns all the fragment names given + all their dependencies"""
    final_names = set(names)
    for name in names:
        dependencies = FRAGMENTS[name][2]
        if dependencies:
            final_names.update(get_all_fragments_names_for(*dependencies))
    return final_names


def reindent(text):
    lines = []
    indent = 0
    for line in text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        count_open = line.count('{')
        count_close = line.count('}')
        if count_close > count_open:
            indent -= 1
        line = '  ' * indent + line.strip()
        lines.append(line)
        if count_open > count_close:
            indent += 1

    return '\n'.join(lines)


def compose_fragments(*names, **kwargs):
    """Take the names of fragments to return, resolving dependencies"""

    return ''.join(
        [
            """
                fragment %(name)s on %(model)s {
                    %(content)s
                }
            """ % {
                'name': name,
                'model': FRAGMENTS[name][0],
                'content': FRAGMENTS[name][1],
            }
            for name in get_all_fragments_names_for(*names)
        ]
    )


def compose_query(query, *fragments):
    return reindent(query) + '\n\n' + reindent(compose_fragments(*fragments))


def compose_variables(variables):
    """Will convert a dict of variables in a string ready to pass to the
    request to the graphql api endpoint.
    Note that although variables in the query must start with a `$`, they should NOT have
    this prefix in the given dict/returned string"""

    return json.dumps(variables)


def fetch_graphql(gh, query, variables=None, name=None, debug_context=None):
    """Call the graphql endpoint for a query.
    `query` must be a string representing a query ready to pass,
    and `variables` could be a string ready to pass, or a dictionnary
    that has to be converted"""

    if variables is None:
        variables = {}

    if isinstance(variables, dict):
        variables = compose_variables(variables)

    logger.info('Querying "%s" on GraphQL with %s (context: %s)', name, variables, debug_context)
    result = gh.graphql.post(query=query, variables=variables)

    if result.get('errors'):
        for error in result.errors:
            if 'Something went wrong while executing your query' in error.get('message', ''):
                if logger.level <= logging.INFO:
                    logger.error(
                        '==> `GraphQLGithubInternalError` raised'
                    ),
                else:
                    logger.error(
                        '`GraphQLGithubInternalError` raised when querying "%s" on GraphQL with "%s" (context: %s)',
                        name,
                        variables,
                        debug_context
                    )
                raise GraphQLGithubInternalError(result)

        for error in result.errors:
            complexity = check_complexity_error(error.get('message'))
            if complexity:
                if logger.level <= logging.INFO:
                    logger.error(
                        '==> `GraphQLComplexityError` (%s > %s) raised',
                        complexity[0],
                        complexity[1],
                     ),
                else:
                    logger.error(
                        '`GraphQLComplexityError` (%s > %s) raised when querying "%s" on GraphQL with "%s" (context: %s)',
                        complexity[0],
                        complexity[1],
                        name,
                        variables,
                        debug_context
                    )
                raise GraphQLComplexityError(result, complexity)

        if logger.level <= logging.INFO:
            logger.error(
                '==> `GraphQLError` raised: %s',
                result.errors
            )
        else:
            logger.error(
                '`GraphQLError` raised when querying "%s" on GraphQL with "%s" (context: %s): %s',
                name,
                variables,
                debug_context,
                result.errors,
            )
        raise GraphQLError(result)

    return convert_ids_from_graphql_result(result.data)


def convert_ids_from_graphql_result(data):
    """Recursively called on all dicts in the data to find for
    `idb64` keys, to convert then to a github_id, replacing the entry
    with `id` key """

    for key, value in list(data.items()):
        if isinstance(value, dict):
            data[key] = convert_ids_from_graphql_result(value)
        elif isinstance(value, list):
            data[key] = [convert_ids_from_graphql_result(entry) for entry in value]
        elif key == 'idb64':
            data['id'] = decode_graphql_id(value)
            del data['idb64']

    return data


def check_complexity_error(message):
    """If the message is about too big complexity of the query, return
    the actual complexity of the query and the max allowed, else returns False"""
    match = RE_COMPLEXITY.match(message)
    if match:
        return map(int, match.groups())
    return False
