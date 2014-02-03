github-issues-manager
=====================

A Django project to manage github issues

*WORK-IN-PROGRESS*

Note:

To run async tasks, you must have a redis running on default host:port, go in your venv at the root of the git project, and run:

```
DJANGO_SETTINGS_MODULE=gim_project.settings limpyd-jobs-worker --worker-class=core.tasks.base.Worker --queues=edit-issue-state,edit-issue-comment,edit-pr-comment,edit-label,update-issue-tmpl,check-repo-events,fetch-issue-by-number,first-repository-fetch,repository-fetch-step2,fetch-available-repos,check-repo-hook,update-repo,update-graphs-data,update-pull-requests,fetch-unfetched-commits,fetch-closed-issues,reset-issue-activity,reset-repo-counters --pythonpath gim_project
```

(you may want to run many workers by repeating the line above in many terms, it's really faster, notably for the `update-issue-tmpl` queue)

Wana talk ? [![Gitter chat](https://badges.gitter.im/twidi/github-issues-manager.png)](https://gitter.im/twidi/github-issues-manager)

[![Bitdeli Badge](https://d2weczhvl823v0.cloudfront.net/twidi/github-issues-manager/trend.png)](https://bitdeli.com/free "Bitdeli Badge")

