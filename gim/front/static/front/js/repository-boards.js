$().ready(function() {

    var Board = {
        $container: $('#board-columns'),
        container: null,
        $columns: $('.board-column'),

        selector: {
            $select: $('#board-selector'),

            format_option: function(state, $container) {
                var $option = $(state.element);
                if (!$option.attr('value')) { return state.text; }
                var nb_columns = $option.data('columns');
                $container.attr('title', $option.attr('title'));
                $container.append($('<span/>').text($option.data('name')));
                $container.append($('<span style="float: right"/>').text(nb_columns + ' columns'));
            }, // format_option

            format_selection: function(state, $container) {
                var $option = $(state.element);
                if (!$option.attr('value')) { return state.text; }
                return 'Current board: <strong>' + $option.data('name') + '</strong>';
            }, // format_selection

            on_change: function(ev) {
                var url = $(this.options[this.selectedIndex]).data('url');
                if (url) { window.location.href = url; }
            }, // on_change

            init: function() {
                Board.selector.$select.select2({
                    placeholder: 'Select a board',
                    formatResult: Board.selector.format_option,
                    formatSelection: Board.selector.format_selection,
                    dropdownCssClass: 'board-selector'
                }).on('change', Board.selector.on_change);

                if (!Board.selector.$select.val()) {
                    Board.selector.$select.select2('open');
                }
            } // init

        }, // Board.selector

        arranger: {
            $input: $('#board-columns-arranger'),
            $holder: $('#board-columns-arranger-holder'),
            init_done: false,
            data: [],
            default_data: [],
            on_change: function(ev) {
                var keys = ev.val,
                    indexes = {};
                for (var i = 0; i < keys.length; i++) {
                    var key = keys[i];
                    indexes[key] = i + 1; // start at 1 to avoid 0, by default
                }
                Board.lists.rearrange(indexes);
            }, // on_change

            on_button_action_click: function () {
                switch(this.value) {
                    case "reset":
                        Board.arranger.$input.select2('data', Board.arranger.default_data, true);
                        break;
                    case "clear":
                        Board.arranger.$input.select2('data', [], true);
                        break;
                    case "close":
                        Board.arranger.$holder.collapse('hide');
                        break;
                }
                return false;
            },

            init_select2: function() {
                if (Board.arranger.init_done) { return; }
                Board.arranger.data = Board.$columns.map(function() {
                    var $column = $(this),
                        $list = $column.children('.issues-list-container'),
                        key = $list.data('key'),
                        data = {
                            id: key,
                            text: $list.children('.issues-list-title').text().trim()
                        };
                    if (!$column.hasClass('hidden')) {
                        Board.arranger.default_data.push(data);
                    }
                    this.board_key = key;
                    return data;
                }).toArray();

                Board.arranger.$input.select2({
                    data: Board.arranger.data,
                    multiple: true,
                    formatNoMatches: function(term) { return term ? 'No matching column' : 'No more columns to display'; },
                    change: Board.arranger.on_change
                }).on("change", Board.arranger.on_change)
                .select2("container").find("ul.select2-choices").sortable({
                    containment: 'parent',
                    start: function() {Board.arranger.$input.select2("onSortStart"); },
                    update: function() {Board.arranger.$input.select2("onSortEnd"); }
                });

                Board.arranger.$holder.find('button').on('click', Ev.stop_event_decorate(Board.arranger.on_button_action_click));
            }, // init_select2,

            remove_column: function(key) {
                Board.arranger.init_select2();
                var data = Board.arranger.$input.select2('data');
                Board.arranger.$input.select2(
                    'data',
                    $.grep(data, function(entry) { if (entry.id != key) { return entry }}),
                    true
                );
            }, // remove_column

            init: function() {
                if (!Board.arranger.$input.length) { return; }
                Board.arranger.$holder.one('shown.collapse', Board.arranger.init_select2);
            } // init

        }, // Board.arranger

        lists: {
            lists_selector: '.issues-list-container',
            filters_selector: '.issues-filters',
            loading: false,

            is_column_visible: function(column, container_left, container_right) {
                if (typeof container_left === 'undefined') {
                    container_left = Board.container.scrollLeft;
                    container_right = container_left + Board.container.offsetWidth;
                }
                return (column.offsetLeft <= container_right && column.offsetLeft + column.offsetWidth >= container_left);
            }, // is_column_visible

            load_visible: function(delay) {
                if (!delay && Board.lists.loading){
                    delay = 10;
                }
                if (delay) {
                    setTimeout(function () {
                        requestNextAnimationFrame(function () {
                            Board.lists.load_visible();
                        });
                    }, delay);
                    return;
                }

                Board.lists.loading = true;
                var $columns = Board.$columns.not('.hidden, .loaded'),
                    container_left = Board.container.scrollLeft,
                    container_right = container_left + Board.container.offsetWidth;
                for (var i = 0; i < $columns.length; i++) {
                    var column = $columns[i], $column, $issues_list_node, $filters_node, url;

                    if (!Board.lists.is_column_visible(column, container_left, container_right)) { continue; }

                    $column = $(column);
                    $issues_list_node = $column.children(Board.lists.lists_selector);
                    $filters_node = $column.children(Board.lists.filters_selector);
                    url = $issues_list_node.children('.issues-list').data('url');
                    $column.addClass('loaded');

                    IssuesFilters.reload_filters_and_list(url, $filters_node, $issues_list_node, true);
                }
                Board.lists.loading = false;

            }, // load_visible

            rearrange: function(indexes) {
                for (var i = 0; i < Board.$columns.length; i++) {
                    var column = Board.$columns[i],
                        $column = $(column);
                    if (typeof indexes[column.board_key] != 'undefined') {
                        $column.css('order', indexes[column.board_key]);
                        $column.removeClass('hidden');
                    } else {
                        $column.css('order', -1);
                        $column.addClass('hidden');
                    }
                }
                window.PanelsSwpr.update_panels_order();
                Board.lists.load_visible();
            }, // rearrange

            on_closer_click: function () {
                Board.arranger.remove_column($(this).prev(Board.lists.lists_selector).data('key'));
                return false;
            }, // on_closer_click

            init: function() {
                if (!Board.$columns.length) { return; }
                Board.lists.load_visible();
                $('.board-column-closer').on('click', Ev.stop_event_decorate(Board.lists.on_closer_click));
                jwerty.key('x', IssuesList.on_current_list_key_event('close'));

            } // init

        }, // Board.lists

        on_scroll: function(ev) {
            Board.lists.load_visible(500);
        }, //scroll

        init: function() {
            Board.container = Board.$container[0];
            Board.lists.init();
            Board.selector.init();
            Board.arranger.init();
            Board.container.addEventListener('scroll', Board.on_scroll); // no jquery overhead
        } // init

    }; // Board

    IssuesList.prototype.close = function close () {
        Board.arranger.remove_column(this.$container_node.data('key'));
        return false;
    };

    Board.init();
});
