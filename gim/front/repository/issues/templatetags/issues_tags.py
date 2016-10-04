from repoze.lru import LRUCache

from adv_cache_tag.tag import CacheTag

from django import template
from django.template import TemplateSyntaxError
from django.template.base import Node
from django.utils.html import strip_spaces_between_tags

register = template.Library()


@register.filter
def edit_field_url(issue, field):
    return issue.edit_field_url(field)


class IssueCacheTag(CacheTag):
    class Meta(CacheTag.Meta):
        versioning = True
        compress = True
        compress_spaces = True
        include_pk = True
        cache_backend = 'issues_tag'
        internal_version = "13.pre10"

IssueCacheTag.register(register, 'issue_cache')


class InjectRepositoryInIssue(Node):
    template = template.Template("""
        <div class="issue-item-repository{% if repository.private %} is-private{% endif %}">
            {% if repository.subscription %}
                <a href="{{ repository.get_absolute_url }}" title="View dashboard">
                    {% if repository.private %}<i class="fa fa-lock" title="This repository is private"> </i>{% endif %}
                    {{ repository.full_name }}
                </a>
                <a href="{{ repository.github_url }}" target="_blank" title="View on Github"><i class="fa fa-github"> </i></a>
            {% else %}
                <a href="{{ repository.github_url }}" target="_blank" title="View on Github">
                    {% if repository.private %}<i class="fa fa-lock" title="This repository is private"> </i>{% endif %}
                    {{ repository.full_name }}
                    <i class="fa fa-github"> </i>
                </a>
            {% endif %}
        </div>
    """.strip())

    # to avoid recompute same repository too often
    cache = LRUCache(1000)

    def __init__(self, nodelist, main_repository, issue_repository, force_hide=None, force_show=None):
        self.nodelist = nodelist
        self.main_repository = main_repository
        self.issue_repository = issue_repository
        self.force_hide = force_hide
        self.force_show = force_show

    def get_repository_header(self, repository):
        result = InjectRepositoryInIssue.cache.get(repository.pk)
        if result is None:
            rendered = self.template.render(template.Context({'repository': repository}))
            result = strip_spaces_between_tags(rendered)
            InjectRepositoryInIssue.cache.put(repository.pk, result)
        return result

    def render(self, context):
        output = self.nodelist.render(context).strip()

        main_repository = self.main_repository.resolve(context)
        issue_repository = self.issue_repository.resolve(context)

        force_hide, force_show = None, None
        if self.force_hide is not None:
            force_hide = bool(self.force_hide.resolve(context))
        if self.force_show is not None:
            force_show = bool(self.force_show.resolve(context))

        # force_show wins if both are True
        if force_show or main_repository != issue_repository and not force_hide:
            header = self.get_repository_header(issue_repository)

            # Add the `with-repository` class to the main `issue-item` tag
            sep1 = 'issue-item'
            before, after = output.split(sep1, 1)
            parts = [before, sep1, ' with-repository']

            # Add the repository block before the issue header
            sep2 = '<div class="issue-item-header"'
            before, after = after.split(sep2, 1)
            parts.extend([before, header, sep2, after])

            output = ''.join(parts)

        return output


@register.tag
def inject_repository_in_issue_item(parser, token):
    bits = token.split_contents()
    bits_len = len(bits)

    if bits_len < 3:
        raise TemplateSyntaxError("'inject_repository_in_issue_item' tag takes at least 2 arguments")

    __, main_repository, issue_repository = bits[:3]

    force_hide = None
    force_show = None

    if bits_len > 3:
        if bits_len > 5:
            raise TemplateSyntaxError("'inject_repository_in_issue_item' tag takes at max 4 arguments")

        error = False
        for force_bit in bits[3:]:
            if force_bit.startswith('force_hide='):
                if force_hide is not None:
                    error = True
                    break
                force_hide = force_bit[11:]
            elif force_bit.startswith('force_show='):
                if force_show is not None:
                    error = True
                    break
                force_show = force_bit[11:]
            else:
                error = True
                break

        if error:
            raise TemplateSyntaxError("'inject_repository_in_issue_item' tag `force` parts must start with `force_hide=` and/or `force_show`=")

    nodelist = parser.parse(('end_inject_repository_in_issue_item',))

    parser.delete_first_token()

    return InjectRepositoryInIssue(
        nodelist,
        parser.compile_filter(main_repository),
        parser.compile_filter(issue_repository),
        force_hide=parser.compile_filter(force_hide) if force_hide is not None else None,
        force_show=parser.compile_filter(force_show) if force_show is not None else None,
    )
