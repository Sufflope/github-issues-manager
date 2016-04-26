$().ready(function() {

    var $document = $(document);

    var DashboardWidget = Class.$extend({
        __init__: function(id, change_selector) {
            this.id = id;
            this.selector = '#' + this.id;
            this.change_selector = this.selector + ' ' + change_selector;
            this.refresh();
            this.init_events();
        }, // __init__

        set_node: function() {
            this.$node = $(this.selector);
        }, // set_node

        refresh: function() {
            this.set_node();
            if (!this.$node.length) { return; }
            this.prepare_content();
        }, // refresh

        prepare_content: function() {

        }, // prepare_content

        reload: function() {
            var $mask = $('<div class="loading-mask"><p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p></div>');
            this.$node.append($mask);
            $(this.selector).trigger('reload');
        }, // reload

        init_events: function() {
            var widget = this;
            $document.on('reloaded', this.selector, function() {
                widget.refresh();
            });
            if (this.change_selector) {
                $document.on('change', this.change_selector, function() {
                    widget.reload();
                });
            }
        }

    }); // DashboardWidget

    var MilestonesDashboardWidget = DashboardWidget.$extend({
        __init__ : function() {
            this.$super("milestones", 'input[name^=show]');
        }, // __init__
        init_events: function() {
            this.$super();
            $document.on('click', '#milestones a[data-toggle=collapse]', function(ev) {
                ev.preventDefault();
            });
        } // init_events
    }); // MilestonesDashboardWidget

    var LabelsDashboardWidget = DashboardWidget.$extend({
        __init__ : function() {
            this.$super("labels", 'input[name^=show]');
        } // __init__
    }); // LabelsDashboardWidget

    var milestone_widget = MilestonesDashboardWidget();
    LabelsDashboardWidget();

    window.MilestoneForm = {
        $modal: $('#milestone-edit-form'),
        $modal_body: $('#milestone-edit-form .modal-body'),
        $modal_footer: $('#milestone-edit-form .modal-footer'),
        $modal_submit: $('#milestone-edit-form .modal-footer button.submit'),
        $modal_delete: $('#milestone-edit-form .modal-footer button.delete'),
        get_form: function() {
            return $('#milestone-form');
        },
        update: function(timeout) {
            var $form = MilestoneForm.get_form();
            MilestoneForm.$modal_delete.toggle(!!$form.data('delete-url'));
            if (timeout) {
                setTimeout(MilestoneForm.delayed_update, timeout);
            } else {
                MilestoneForm.delayed_update();
            }
            $form.find('.input-append.due_on').datepicker({
                format: "yyyy-mm-dd",
                weekStart: 1,
                orientation: "auto left",
                autoclose: true
            }).data('datepicker').picker.addClass('datepicker-due_on');
        },
        delayed_update: function() {
            MilestoneForm.get_form().find('[name=open]').iButton({
                labelOn: 'Open',
                labelOff: 'Closed',
                className: 'open-state',
                handleWidth: 24
            });
        },
        on_clear_due_on_click: function(ev) {
            var $parent = $(this).parent();
            $parent.find('input').val('');
            $parent.datepicker('hide');
            ev.stopPropagation();
        },
        on_modal_hide: function(ev) {
            MilestoneForm.$modal_body.scrollTop(0);
            MilestoneForm.$modal_footer.find('.alert').remove();
        },
        on_modal_hidden: function(ev) {
            MilestoneForm.$modal_delete.popover('hide');
        },
        init_modal: function(ev) {
            MilestoneForm.$modal.modal({
                backdrop: 'static',
                show: false
            }).on('hide.modal', MilestoneForm.on_modal_hide)
              .on('hidden.modal', MilestoneForm.on_modal_hidden);
        },
        update_modal_body_and_show: function($link, html) {
            MilestoneForm.$modal_body.html(html);
            MilestoneForm.$modal.modal('show');
            MilestoneForm.update(200);
            $link.removeClass('loading');
        },
        on_load_done: function($link, data) {
            MilestoneForm.update_modal_body_and_show($link, data);
        },
        on_load_failed: function($link) {
            MilestoneForm.update_modal_body_and_show($link, '<div class="alert alert-error">A problem prevented us to display the form</div>');
        },
        on_link_click: function(ev) {
            ev.preventDefault();
            ev.stopPropagation();

            var $link = $(this);

            $link.addClass('loading');

            $.get($link.attr('href'))
                .done(function(data) {
                    MilestoneForm.on_load_done($link, data);
                })
                .fail(function(data) {
                    MilestoneForm.on_load_failed($link);
                });
        },
        redraw_content: function() {
            milestone_widget.reload();
            MilestoneForm.$modal.modal('hide');
        },
        on_submit_done: function(data) {
            if (data.substr(0, 6) == '<form ') {
                // we have an error, the whole form is returned
                var $form = MilestoneForm.get_form();
                $form.replaceWith(data);
                MilestoneForm.update();
                MilestoneForm.$modal_body.scrollTop(0);
            } else {
                // no error, we reload the milestone widget
                MilestoneForm.redraw_content();
            }
            MilestoneForm.$modal_submit.removeClass('loading');
        },
        on_submit_failed: function() {
            MilestoneForm.$modal_submit.removeClass('loading');
            MilestoneForm.$modal_footer.prepend('<div class="alert alert-error">A problem prevented us to save the milestone</div>');
        },
        on_form_submit: function(ev) {
            ev.preventDefault();
            ev.stopPropagation();
            MilestoneForm.$modal_submit.addClass('loading');
            MilestoneForm.$modal_footer.find('.alert').remove();
            var $form = MilestoneForm.get_form();
            $.post($form.attr('action'), $form.serialize())
                .done(MilestoneForm.on_submit_done)
                .fail(MilestoneForm.on_submit_failed);
        },
        on_cancel_deletion: function(ev) {
            MilestoneForm.$modal_delete.popover('hide');
        },
        on_delete_done: function(data) {
            MilestoneForm.redraw_content();
            MilestoneForm.$modal_delete.removeClass('loading');
        },
        on_delete_failed: function() {
            MilestoneForm.$modal_delete.removeClass('loading');
            MilestoneForm.$modal_footer.prepend('<div class="alert alert-error">A problem prevented us to delete this milestone</div>');
        },
        on_confirm_deletion: function(ev) {
            MilestoneForm.$modal_delete.popover('hide');
            MilestoneForm.$modal_delete.addClass('loading');
            var $form = MilestoneForm.get_form(),
                url = $form.data('delete-url'),
                data = {
                    csrfmiddlewaretoken: $form[0].csrfmiddlewaretoken.value
                };
            if (url && data.csrfmiddlewaretoken) {
                $.post(url, data)
                    .done(MilestoneForm.on_delete_done)
                    .fail(MilestoneForm.on_delete_failed);
            } else {
                MilestoneForm.on_delete_failed();
            }
        },
        init_deletion: function() {
            MilestoneForm.$modal_delete.popover();
            MilestoneForm.$modal_footer.on('click', '.cancel-deletion', MilestoneForm.on_cancel_deletion);
            MilestoneForm.$modal_footer.on('click', '.confirm-deletion', MilestoneForm.on_confirm_deletion);
        },
        init: function() {
            MilestoneForm.init_modal();
            $document.on('click', '#milestones .edit-link', MilestoneForm.on_link_click);
            $document.on('submit', '#milestone-form', MilestoneForm.on_form_submit);
            $document.on('click', '#milestone-form .field-due_on .add-on:last-child', MilestoneForm.on_clear_due_on_click);
            MilestoneForm.$modal_submit.on('click', MilestoneForm.on_form_submit);
            MilestoneForm.init_deletion();
        }
    }; // MilestoneForm

    window.HookToggleForm = {
        get_form: function() {
            return $('#hook-toggle-form');
        },
        get_button: function($form) {
            return $form.parent().find('a.btn-loading');
        },
        on_button_click: function(ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var $form = HookToggleForm.get_form(),
                $button = HookToggleForm.get_button($form);
            if ($button.hasClass('loading')) { return; }
            $button.addClass('loading');
            $button.closest('li').addClass('disabled');
            $.post($form.attr('action'), $form.serialize())
                .done(HookToggleForm.on_submit_done)
                .fail(HookToggleForm.on_submit_failed);
        },
        on_submit_failed: function() {
            var $form = HookToggleForm.get_form(),
                $button = HookToggleForm.get_button($form);
            $button.removeClass('loading');
            $button.closest('li').addClass('disabled');
        },
        on_submit_done: function(data) {
            var $form = HookToggleForm.get_form();
            $form.parent().replaceWith(data);
        },
        init: function() {
            $document.on('click', '.hook-block a.btn-loading', HookToggleForm.on_button_click);
        }
    }; // HookToggleForm
    
    var ChartManager = {
        $modal: $('#milestone-graph-container'),
        $modal_milestone_select: $('#milestone-graph-selector'),
        $modal_metric_select: $('#milestone-graph-metric-selector'),
        $modal_body: null,
        current_number: null,
        current_metric: null,

        on_milestone_metric_click: function(ev) {
            ev.preventDefault();
            var $link = $(this),
                url = $link.data('url'),
                number = $link.parent().data('number');
            ChartManager.open_chart(number, url);
        }, // on_milestone_metric_click
        
        open_chart: function(number, graph_url) {
            ChartManager.$modal_body.html('<p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p>');
            ChartManager.$modal_milestone_select.select2('val', number);
            ChartManager.$modal.modal('show');
            $.ajaxSetup({cache: true});
            $.ajax({
                type: 'GET',
                url: graph_url + '?metric=' + ChartManager.current_metric,
                cache: true
            }).done($.proxy(ChartManager.on_chart_load_success, {number: ChartManager.current_number}))
                .fail(ChartManager.on_chart_load_failure)
                .always(function() { $.ajaxSetup({cache: false}); });
        }, // open_chart

        on_chart_load_success: function(data) {
            if (this.number != ChartManager.current_number) { return; }
            ChartManager.$modal_body.html(data);
        }, // on_chart_load_success

        on_chart_load_failure: function(xhr, data) {
            ChartManager.$modal_body.find('.empty-area').text('Something sent wrong :(');
        }, // on_chart_load_failure

        prepare_selectors: function () {
            var format = function(state, include_title) {
                if (state.children) {
                    return state.text.charAt(0).toUpperCase() + state.text.substring(1) + ' milestones';
                }
                var data = all_milestones[state.id];
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
            ChartManager.$modal_metric_select.select2();
        }, // prepare_selectors

        on_milestone_selector_change: function(ev) {
            ev.preventDefault();
            var number = ChartManager.$modal_milestone_select.val(),
                url = all_milestones[number].graph_url;
            ChartManager.open_chart(number, url);
        }, // on_milestone_selector_change

        on_metric_selector_change: function(ev) {
            ChartManager.current_metric = ChartManager.$modal_metric_select.val();
            ChartManager.on_milestone_selector_change(ev);
        }, // on_metric_selector_change

        init: function() {
            ChartManager.$modal_body = ChartManager.$modal.find('.modal-body');
            $document.on('click', '#milestones a.metric-stats', ChartManager.on_milestone_metric_click);
            ChartManager.prepare_selectors();
            ChartManager.$modal_milestone_select.on('change', ChartManager.on_milestone_selector_change);
            ChartManager.$modal_metric_select.on('change', ChartManager.on_metric_selector_change);
        } // init
    }; // ChartManager
    ChartManager.init();

    var $body = $('body');
    IssuesByDayGraph.fetch_and_make_graph($body.data('repository-id'), 40, $body.find('main > .row-header .area-top'));
});
