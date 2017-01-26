$().ready(function() {
    var get_graph = function () {
        var $repo_node = $('#subscribed_repositories .box-section[data-repo-id]:not(.has-graph):not(.hidden)').first();
        if (!$repo_node.length) {
            $repo_node = $('#subscribed_repositories .box-section[data-repo-id]:not(.has-graph)').first();
        }
        if ($repo_node.length) {
            IssuesByDayGraph.fetch_and_make_graph($repo_node.data('repo-id'), 40, $repo_node.children('.news-content'), function() {
                $repo_node.addClass('has-graph');
                get_graph();
            });
        }
    };
    get_graph();
});
