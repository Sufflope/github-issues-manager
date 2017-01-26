(function() {
    var ChartManager = {
        $modal: $('#milestone-graph-container'),
        $modal_milestone_select: $('#milestone-graph-selector'),
        $modal_metric_select: $('#milestone-graph-metric-selector'),
        $modal_issues_type_select: $('#milestone-issues-type-selector'),
        $modal_body: null,
        current_number: null,
        current_metric: null,
        current_issues_type: null,
        all_milestones: $('body').data('all-milestones'),
        plotly: {
            loading: false,
            loaded: false
        },

        open_from_link: function(ev) {
            ev.preventDefault();
            var $link = $(this),
                url = $link.data('url'),
                number = $link.data('number'),
                metric = $link.data('metric');
            ChartManager.open_chart(number, url, metric);
        }, // open_from_link

        open_chart: function(number, graph_url, metric) {
            if (metric) { ChartManager.change_metric(metric); }
            ChartManager.$modal_body.html('<p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p>');
            ChartManager.$modal_milestone_select.select2('val', number);
            ChartManager.$modal.modal('show');
            $.ajaxSetup({cache: true});
            $.ajax({
                type: 'GET',
                url: graph_url + '?metric=' + ChartManager.current_metric + '&issues=' + ChartManager.current_issues_type,
                cache: true
            }).done($.proxy(ChartManager.on_chart_load_success, {number: ChartManager.current_number}))
                .fail(ChartManager.on_chart_load_failure)
                .always(function() { $.ajaxSetup({cache: false}); });
            ChartManager.load_plotly();
        }, // open_chart

        close_chart: function() {
            ChartManager.$modal.modal('hide');
        }, // close_chart

        on_chart_load_success: function(data) {
            if (this.number != ChartManager.current_number) { return; }
            ChartManager.$modal_body.html(data);
            setTimeout(ChartManager.run_chart, 100);
        }, // on_chart_load_success

        load_plotly: function() {
            if (ChartManager.plotly.loading || ChartManager.plotly.loaded) { return; }
            ChartManager.plotly.loading = true;
            AppGlobal.loadScript(AppGlobal.InitData.plotly_statics.js, function() {
                ChartManager.plotly.loaded = true;
                ChartManager.plotly.loading = false;
            });
        }, // load_plotly

        run_chart: function() {
            if (!ChartManager.plotly.loaded) {
                ChartManager.load_plotly();
                setTimeout(ChartManager.run_chart, 100);
                return;
            }
            var $graph = $('#milestone-graph');
            $graph.on('plotly_afterplot', function(ev) {
                // remove spinner
                $graph.find('.empty-area').remove();
                // remove unwanted buttons
                var $button_groups = $('.modebar-group'),
                    $buttons = $button_groups.find('a');
                for (var i = 1; i < $buttons.length; i++) {
                    $buttons[i].remove();
                }
                for (var j = 1; j < $button_groups.length; j++) {
                    $button_groups[j].remove();
                }
            });

            var hover = false;
            var hover_right = false;
            var $hover_text_node = null;

            function force_hover_text_left() {
                if (!hover) { return; }
                if ($hover_text_node.attr('text-anchor') == 'end') {
                    if (!hover) { return; }
                    hover_right = true;
                    try {
                        var width = $hover_text_node[0].getBBox().width;
                        $hover_text_node.attr('x', $hover_text_node.attr('x') - width);
                        $hover_text_node.attr('text-anchor', 'start');
                    } catch (e) {}
                    if (!hover) { return; }
                }
                if (hover_right) {
                    requestNextAnimationFrame(force_hover_text_left);
                }
            }

            $graph.on('plotly_hover', function() {
                hover = true;
                $hover_text_node = $graph.find('.hoverlayer .hovertext text');
                force_hover_text_left();
            });
            $graph.on('plotly_unhover', function() {
                hover = false;
                hover_right = false;
            });

            Plotly.plot('milestone-graph', $graph.data('graph-graphs'), $graph.data('graph-layout'));
        }, /// run_chart

        on_chart_load_failure: function(xhr, data) {
            ChartManager.$modal_body.find('.empty-area').text('Not enough data to generate this chart');
        }, // on_chart_load_failure

        change_metric: function(metric) {
            ChartManager.current_metric = metric;
            ChartManager.$modal_metric_select.select2("val", metric);
        }, // change_metric

        change_issues_type: function(issues_type) {
            ChartManager.current_issues_type = issues_type;
            ChartManager.$modal_issues_type_select.select2("val", issues_type);
        }, // change_issues_type

        prepare_selectors: function () {
            var format = function(state, include_title) {
                    if (state.children) {
                        return state.text.charAt(0).toUpperCase() + state.text.substring(1) + ' milestones';
                    }
                    var data = ChartManager.all_milestones[state.id];
                    if (data) {
                        var result = '<i class="fa fa-tasks text-' + data.state + '"> </i> <strong>' + (data.title.length > 50 ? data.title.substring(0, 45) + '…' : data.title);
                        if (include_title) {
                            var title = data.state.charAt(0).toUpperCase() + data.state.substring(1) + ' milestone';
                            if (data.state == 'open' && data.due_on) {
                                title += ', due on ' + data.due_on;
                            }
                            result = '<div title="' + title + '">' + result + '</div>';
                        }
                        return result;
                    } else {
                        return '<i class="fa fa-tasks"> </i> No milestone';
                    }
                }, // format
                matcher =  function(term, text) {
                    var last = -1;
                    term = term.toLowerCase();
                    text = text.toLowerCase();
                    for (var i = 0; i < term.length; i++) {
                        last = text.indexOf(term[i], last+1);
                        if (last == -1) { return false; }
                    }
                    return true;
                }; // matcher

            ChartManager.$modal_milestone_select.select2({
                formatSelection: function(state) { return format(state, false); },
                formatResult:  function(state) { return format(state, true); },
                escapeMarkup: function(m) { return m; },
                dropdownCssClass: 'select2-milestone',
                matcher: matcher
            });

            ChartManager.current_metric = ChartManager.$modal_metric_select.val();
            ChartManager.current_issues_type = ChartManager.$modal_issues_type_select.val();
            ChartManager.$modal_metric_select.select2();
            ChartManager.$modal_issues_type_select.select2();
        }, // prepare_selectors

        on_milestone_selector_change: function(ev) {
            ev.preventDefault();
            var number = ChartManager.$modal_milestone_select.val(),
                url = ChartManager.all_milestones[number].graph_url;
            ChartManager.open_chart(number, url);
        }, // on_milestone_selector_change

        on_metric_selector_change: function(ev) {
            ChartManager.current_metric = ChartManager.$modal_metric_select.val();
            ChartManager.on_milestone_selector_change(ev);
        }, // on_metric_selector_change

        on_issues_type_selector_change: function(ev) {
            ChartManager.current_issues_type = ChartManager.$modal_issues_type_select.val();
            ChartManager.on_milestone_selector_change(ev);
        }, // on_metric_selector_change

        init: function() {
            ChartManager.$modal_body = ChartManager.$modal.find('.modal-body');
            ChartManager.prepare_selectors();
            ChartManager.$modal_milestone_select.on('change', ChartManager.on_milestone_selector_change);
            ChartManager.$modal_metric_select.on('change', ChartManager.on_metric_selector_change);
            ChartManager.$modal_issues_type_select.on('change', ChartManager.on_issues_type_selector_change);
        } // init
    }; // ChartManager
    AppGlobal.ChartManager = ChartManager;

    $().ready(function() {
        ChartManager.init();
    });

})();
