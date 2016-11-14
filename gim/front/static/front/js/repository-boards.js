$().ready(function() {

    var $document = $(document),
        $body = $('body'),
        body_id = $body.attr('id'),
        main_repository_id = $body.data('repository-id');

    var Board = {
        container_selector: '#board-columns',
        $container: $('#board-columns'),
        container: null,
        $columns: $('.board-column'),
        base_url: null,
        mode: null,
        editable: false,
        dimensions: {
            scrollLeftMax: 0,
            scrollWidth: 0
        },

        selector: {
            $select: $('#board-selector'),

            format_option: function(state, $container) {
                var $option = $(state.element),
                    value = $option.attr('value');
                if (value == 'labels-editor') {
                    $container.addClass('labels-editor-link');
                    value = null;
                }
                if (value == 'project-creator') {
                    $container.addClass('project-creator-link');
                    value = null;
                }
                if (!value) { return state.text; }
                var nb_columns = $option.data('columns');
                $container.attr('title', $option.attr('title'));
                $container.append($('<span/>').text($option.data('name')));
                $container.append($('<span style="float: right"/>').text(nb_columns + ' column' + (nb_columns > 1 ? 's' : '')));
                if ($option.data('first-of-mode')) {
                    $container.addClass('first-of-mode');
                }
            }, // format_option

            format_selection: function(state, $container) {
                var $option = $(state.element),
                    value = $option.attr('value');
                if (value == 'labels-editor' || value == 'project-creator') {
                    return '';
                }
                if (!value) { return state.text; }
                return 'Current board: <strong>' + $option.data('name') + '</strong>';
            }, // format_selection

            on_change: function(ev) {
                var url = $(this.options[this.selectedIndex]).data('url');
                if (url) { window.location.href = url; }
            }, // on_change

            on_update_project_alert: function(topic, args, kwargs) {
                var is_current = (Board.mode == 'project' && kwargs.number == Board.$container.data('key'));

                var selector = Board.selector.$select.data('select2');
                if (is_current) {
                    selector.container.find('.select2-chosen > strong').text(kwargs.name);
                }
                var $option = Board.selector.$select.find('option[value=project-' + kwargs.number + ']');

                // create an option if it doesn't exit
                if (!$option.length) {
                    $option = $('<option title="Github project with all its columns"></option>');
                    $option.attr('value', 'project-' + kwargs.number)
                           .attr('data-url', kwargs.url)
                           .text(kwargs.name);
                    var $options = Board.selector.$select.find('option');
                    var $after = null;
                    for (var i = 0; i < $options.length; i++) {
                        var $iter_options = $($options[i]);
                        var value = $iter_options.attr('value');
                        if (typeof value == 'undefined' || value == '') {
                            $after = $iter_options;
                            continue;
                        }
                        if (value.indexOf('auto-') == 0) {
                            $after = $iter_options;
                            continue;
                        }
                        if (value.indexOf('project-') == 0) {
                            var number = parseInt(value.split('-')[1], 10);
                            if (number < kwargs.number) {
                                $after = $iter_options;
                                continue;
                            } else {
                                break;
                            }
                        }
                        if (value.indexOf('labels-') == 0) {
                            break;
                        }
                    }
                    if (!$after || $after.attr('value').indexOf('project-') != 0) {
                        $option.attr('data-first-of-mode', 'true');
                    }
                    if ($after) {
                        $after.after($option);
                    } else {
                        Board.selector.$select.prepend($option);
                    }
                }

                $option.text(kwargs.name)
                       .data('name', kwargs.name)
                       .data('columns', kwargs.nb_columns+1 );

                selector.updateResults();

            }, // on_update_project_alert

            on_delete_project_alert: function(topic, args, kwargs) {
                var $option = Board.selector.$select.find('option[value=project-' + kwargs.number + ']');
                if (!$option.length) { return; }
                $option.remove();
                Board.selector.$select.data('select2').updateResults();
            }, // on_delete_project_alert

            update_project_columns_count: function(project_number, nb_columns) {
                var $option = Board.selector.$select.find('option[value=project-' + project_number + ']');
                if (!$option.length) { return; }
                $option.data('columns', nb_columns);
                Board.selector.$select.data('select2').updateResults();
            }, // update_project_columns_count

            init: function() {
                Board.selector.$select.select2({
                    placeholder: 'Select a board',
                    formatResult: Board.selector.format_option,
                    formatSelection: Board.selector.format_selection,
                    dropdownCssClass: 'board-selector'
                }).on('change', Board.selector.on_change);

                if (Board.selector.$select.data('auto-open')) {
                    Board.selector.$select.select2('open');
                }
            } // init

        }, // Board.selector

        arranger: {
            updating_ids: {},
            reorder_counter: 0,

            hide_column: function($column) {
                $column.addClass('hidden');
                Board.arranger.on_columns_rearranged();
            }, // hide_column

            restore_hidden: function() {
                $('.board-column.hidden').removeClass('hidden');
                Board.arranger.on_columns_rearranged();
            }, // restore_hidden

            on_column_loaded: function () {
                var $list_container_node = $(this);
                requestNextAnimationFrame(function() {
                    var list = IssuesList.get_for_node($list_container_node),
                        $column = $list_container_node.closest('.board-column'),
                        not_loaded = list.$node.hasClass('not-loaded'),
                        front_uuid = list.$node.data('front-uuid'),
                        key = list.$container_node.data('key'),
                        edit_url = list.$node.data('edit-column-url'),
                        $edit_btn = $column.find('.board-column-edit');

                    $column.toggleClass('loaded', !not_loaded).toggleClass('not-loaded', not_loaded).removeClass('loading');

                    if (front_uuid) {
                        $column.attr('data-front-uuid', front_uuid);
                    }

                    $column.data('key', key);
                    $column.attr('data-key', key);

                    if (!not_loaded) {
                        if (Board.mode == 'project' && Board.editable && key != '__none__') {
                            if (edit_url && !$edit_btn.length) {
                                $column.find('.board-column-icons').prepend(
                                    '<a href="#" class="board-column-edit" title="Edit or delete this column"><i class="fa fa-pencil"> </i></a>'
                                );
                            } else if (!edit_url && $edit_btn.length) {
                                $edit_btn.remove();
                            }
                        }
                        Board.arranger.ask_for_reorder();
                    }

                    Board.$columns = $('.board-column');
                });
            }, // on_column_loaded

            on_columns_rearranged: function() {
                PanelsSwapper.update_panels_order();
                Board.lists.load_visible();
                Board.dragger.on_columns_rearranged();
                Board.$columns = $('.board-column');
                Board.arranger.update_sortable();
                Board.selector.update_project_columns_count(Board.$container.data('key'), Board.$columns.length);
            }, // on_columns_rearranged

            on_sortable_create: function(ev, ui) {
                var obj = $(this).data('ui-sortable');
                obj._mouseDrag = Board.dragger._sortable_override_mouse_drag;
                obj._isFloating = Board.arranger._sortable_override_isFloating;
            }, // on_sortable_create

            _sortable_override_isFloating: function( item ) {
                return ( /left|right/ ).test( item.css( "float" ) ) ||
                    ( /inline|table-cell/ ).test( item.css( "display" ) ) ||
                    ( /flex/ ).test( this.element.css( "display" ) );  // line added
            },

            prepare_sortable: function() {
                Board.$container.sortable({
                    scroll: true,
                    scrollSensitivity: 50,
                    scrollSpeed: 50,
                    containment: Board.container_selector,
                    cursor: 'move',
                    tolerance: 'pointer',
                    create: Board.arranger.on_sortable_create,
                    items: '> .board-column.loaded[data-key]:not([data-key=__none__]):not(.edit-mode)',
                    start: Board.arranger.on_drag_start,
                    stop: Board.arranger.on_drag_stop
                }).disableSelection();
            }, // prepare_sortable

            check_movable: function(sortable_node, ui_item) {
                requestNextAnimationFrame(function() {
                    var $column = ui_item,
                        list = $column.find('.issues-list')[0].IssuesList,
                        data = {csrfmiddlewaretoken: $body.data('csrf')},
                        context = {
                            sortable_node: sortable_node,
                            ui_item: ui_item
                        },
                        url;

                    if (list.$node) {
                        url = list.$node.data('can-move-column-url');
                    }

                    if (!url) {
                        $proxy(Board.arranger.on_check_movable_failure, context)();
                    }

                    $.post(url, data)
                        .fail($.proxy(Board.arranger.on_check_movable_failure, context))
                });
            }, // check_movable

            on_check_movable_failure: function(xhr, data) {
                $(this.sortable_node).sortable('cancel');
            }, // on_check_movable_failure

            on_drag_start: function(ev, ui) {
                if (Board.mode == 'project' && Board.editable) {
                    Board.arranger.check_movable(this, ui.item);
                } else {
                    MessagesManager.add_messages([MessagesManager.make_message("Columns positions won't be saved.", 'info')]);
                }
            }, // on_drag_start

            on_drag_stop: function(ev, ui) {
                if (Board.mode == 'project' && Board.editable) {
                    var $column = ui.item,
                        list = $column.find('.issues-list')[0].IssuesList,
                        actual_position = parseInt(list.$node.data('position'), 10) || 1,
                        $previous_column = $column.prev('.board-column'),
                        new_position = parseInt($previous_column.length ? $previous_column.find('.issues-list').data('position') : 0, 10) || 0;

                    if (new_position < actual_position) {
                        new_position ++;
                    }

                    if (new_position != actual_position) {
                        Board.arranger.update_column_position($column, new_position);
                        Board.arranger.remote_move_column(list, actual_position, new_position);
                    }
                }
                Board.arranger.on_columns_rearranged();
            }, // on_drag_stop

            remote_move_column: function(list, actual_position, new_position) {
                var url = list.$node.data('move-column-url'),
                    front_uuid = UUID.generate('waiting'),
                    data = {
                        csrfmiddlewaretoken: $body.data('csrf'),
                        front_uuid: front_uuid,
                        position: new_position
                    },
                    context = {
                        list: list,
                        actual_position: actual_position,
                        new_position: new_position
                    };

                $.post(url, data)
                    .done(function(data) {
                        Board.arranger.ask_for_reorder();
                    })
                    .fail($.proxy(Board.arranger.on_remote_move_column_failure, context))
                    .always(function() {UUID.set_state(front_uuid, '');});

            }, // remote_move_column

            on_remote_move_column_failure: function(xhr, data) {
                if (xhr.status != 409) {
                    MessagesManager.add_messages([MessagesManager.make_message(
                        "We couldn't update the column's position", 'error')]);
                }
                Board.arranger.update_column_position(this.list.$node.closest('.board-column'), this.actual_position);
            }, // on_remote_move_column_failure

            update_column_position: function ($column, position) {
                var list = $column.find('.issues-list')[0].IssuesList,
                    actual_position = parseInt(list.$node.data('position'), 10) || 1,
                    i, $column_to_move, column_to_move_position, column_list, condition, delta;

                if (position == actual_position) {
                    return;
                }

                for (i = 0; i < Board.$columns.length; i++) {
                    $column_to_move = $(Board.$columns[i]);
                    try {
                        column_list = $column_to_move.find('.issues-list')[0].IssuesList;
                        column_to_move_position = parseInt(column_list.$node.data('position'), 10);
                    } catch (e) {
                        continue;
                    }
                    if (position > actual_position) {  // going right
                        // we move to the left all columns between the old position and the new one
                        // excluding the old position (it's the column we move) and including the new one
                        // (the column we move takes its place and the old one is on the left)
                        condition = (column_to_move_position > actual_position && column_to_move_position <= position);
                        delta = -1;
                    } else {
                        // we move to the right all columns between the old position and the new one
                        // including the new position (the column we move takes its place and the old one
                        // is on the right) and excluding the old position (it's the column we move)
                        condition = (column_to_move_position >= position && column_to_move_position < actual_position);
                        delta = 1;
                    }
                    column_to_move_position += delta;
                    column_list.$node.data('position', column_to_move_position);
                    column_list.$node.attr('data-position', column_to_move_position);
                }

                // and update the column
                list.$node.data('position', position);
                list.$node.attr('data-position', position);

                Board.arranger.ask_for_reorder();
            }, // update_column_position

            ask_for_reorder: function() {
                Board.arranger.reorder_counter += 1;
                var counter = Board.arranger.reorder_counter;
                setTimeout(function() {
                    if (counter != Board.arranger.reorder_counter) {
                        // during the way another reorder was asked
                        return;
                    }
                    Board.arranger.reorder();
                }, 100)
            }, // ask_for_reorder

            reorder_compare: function($column1, $column2) {
                return $column1.position - $column2.position;
            }, // reorder_compare

            reorder: function() {
                var columns = [], mapping = {}, i, $column, position, actual_position = 0, moves = [], move, node, container = Board.$container[0], dest;
                // get only columns with position
                for (i = 0; i < Board.$columns.length; i++) {
                    $column = $(Board.$columns[i]);
                    try {
                        position = parseInt($column.find('.issues-list')[0].IssuesList.$node.data('position'), 10);
                    } catch (e) {
                        position = null;
                    }
                    if (position) {
                        $column.dom_position = i; // index in the container
                        $column.actual_position = actual_position; // index in the container for only movable columns
                        $column.position = position;  // from the column db object
                        columns.push($column);
                        mapping[actual_position] = i;  // to use the container child index when moving in place of this column
                        actual_position ++;
                    }
                }
                // sort them
                columns.sort(Board.arranger.reorder_compare);

                // get the moves
                for (var i = 0; i < columns.length; i++) {
                    $column = columns[i];
                    if ($column.actual_position != i) {  // still at the same place
                        moves.push({
                            $column: $column,
                            position: $column.actual_position,
                            to: i
                        });
                    }
                }
                if (moves.length) {

                    // we can now move the columns that need to, in their position order
                    moves.sort(Board.arranger.reorder_compare);
                    for (i = 0; i < moves.length; i++) {
                        move = moves[i];
                        node = move.$column[0];
                        dest = container.children[mapping[move.to]];
                        if (node == dest) {
                            continue;
                        }
                        if (move.to > move.position) {
                            dest = dest.nextSibling; // emulate insertAfter
                        }
                        container.insertBefore(node, dest);
                    }

                }

                // to do even if no changes in order
                Board.update_dimensions();
                Board.arranger.on_columns_rearranged();

            }, // reorder

            update_sortable: function() {
                Board.$container.sortable('refresh');
            }, // update_sortable

            exit_edit_mode: function($column) {
                $column.children('.column-form, .loading-mask').remove();
                $column.removeClass('edit-mode');
                Board.arranger.update_sortable();
            }, // exit_edit_mode

            on_submit: function(ev, on_submit_done, action_name) {
                var $form = $(this), context;
                if ($form.data('disabled')) { return false; }

                context = FormTools.handle_form($form, ev);
                if (context === false) { return false; }

                context.action_name = action_name;

                if (action_name != 'delete') {
                    var $input = $form.find('input[name=name]');

                    if ($input.length && !$input.val().trim()) {
                        $input.after('<div class="alert alert-error">You must enter a name</div>');
                        $form.find('button').removeClass('loading');
                        FormTools.enable_form($form);
                        $input.focus();
                        return false;
                    }
                }

                $form.closest('.board-column')[0].setAttribute('data-front-uuid', context.uuid);

                FormTools.post_form_with_uuid($form, context,
                    on_submit_done,
                    Board.arranger.on_submit_failed
                );

            }, // on_submit

            on_submit_failed: function (xhr, data) {
                if (xhr.status == 409) {
                    // 409 Conflict Indicates that the request could not be processed because of
                    // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                    this.$form.find('button.submit').remove();
                    FormTools.enable_form(this.$form);
                    var $input = this.$form.find('input[name=name]');
                    var msg = 'The column cannot be ' + this.action_name + 'd for now.';
                    if (action_name != 'delete') {
                        msg += ' Copy the name if you need, then cancel and'
                    } else {
                        msg += ' You may'
                    }
                    msg += ' retry in a few seconds.';
                    $input.after('<div class="alert alert-error">' + msg + '</div>');
                    return
                }
                FormTools.enable_form(this.$form);
                this.$form.find('.alert').remove();
                var $input = this.$form.find('input[name=name]');
                $input.after('<div class="alert alert-error">We were unable to ' + this.action_name + ' this column</div>');
                this.$form.find('button').removeClass('loading');
                $input.focus();
            }, // on_submit_failed

            on_edit_click: function() {
                var $column = $(this).closest('.board-column'),
                    url = $column.find('.issues-list').data('edit-column-url'),
                    $mask = IssuesFilters.add_waiting($column),
                    context = {$column: $column, $mask: $mask};

                $column.addClass('edit-mode');
                Board.arranger.update_sortable();

                $.get(url)
                    .done($.proxy(Board.arranger.on_edit_or_delete_loaded, context))
                    .fail($.proxy(Board.arranger.on_edit_or_delete_load_failed, context))
            }, // on_edit_click

            on_edit_or_delete_loaded: function (data) {
                if (!data.trim() || data == 'error') {  // error if 409 from on_edit_or_delete_load_failed
                    Board.arranger.exit_edit_mode(this.$column);
                    return false;
                }
                this.$column.prepend(data);
                this.$mask.addClass('no-spinner');
                if (!$(':input:focus').length) {
                    var $input = this.$column.find('.column-form input[type=text]');
                    if ($input.attr('readonly')) {
                        this.$column.find('.column-form button').first().focus();
                    } else {
                        $input.focus();
                        $input.select();
                    }
                }
            }, // on_edit_or_delete_load_failed

            on_edit_or_delete_load_failed: function (xhr, data) {
                if (xhr.status == 409) {
                    // 409 Conflict Indicates that the request could not be processed because of
                    // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                    return $.proxy(Board.arranger.on_edit_or_delete_loaded, this)(data);
                }
                Board.arranger.exit_edit_mode(this.$column);
                alert('Unable to retrieve the form to edit this column');
            }, // on_edit_or_delete_load_failed

            on_edit_or_delete_cancel_click: function() {
                Board.arranger.exit_edit_mode($(this).closest('.board-column'));
            }, // on_edit_or_delete_cancel_click

            on_edit_submit: function(ev) {
                return Board.arranger.on_submit.bind(this)(ev, Board.arranger.on_edit_submit_done, 'update');
            }, // on_add_submit

            on_edit_submit_done: function (data) {
                var $data = $(data),
                    name = $data.data('name'),
                    $column = $('.board-column[data-front-uuid=' + this.uuid + ']');
                if ($column.length) {
                    $column.find('.column-title').text(name);
                    Board.arranger.exit_edit_mode($column);
                }
            }, // on_submit_done

            on_delete_click: function() {
                var $column = $(this).closest('.board-column'),
                    url = $column.find('.issues-list').data('delete-column-url'),
                    $mask = $column.children('.loading-mask');

                $mask.removeClass('no-spinner');
                $column.children('.column-form').remove();
                $.get(url)
                    .done($.proxy(Board.arranger.on_edit_or_delete_loaded, context))
                    .fail($.proxy(Board.arranger.on_edit_or_delete_load_failed, context))
            },

            on_delete_submit: function(ev) {
                return Board.arranger.on_submit.bind(this)(ev, Board.arranger.on_delete_submit_done, 'delete');
            }, // on_delete_submit

            on_delete_submit_done: function (data) {
                var $column = this.$form.closest('.board-column'),
                    $data = $(data),
                    key = $data.filter('.issues-list-container').data('key'),
                    list;

                try {
                    list = $column.find('.issues-list')[0].IssuesList;

                    if (list) {
                        IssuesList.remove_list(list);
                    }
                } catch (e) {}

                $column.empty().removeClass('create-mode').append($data);
                Board.arranger.on_columns_rearranged();
            }, // on_delete_submit_done

            on_add_click: function() {
                var $empty_column = $('<div class="board-column create-mode"></div>'),
                    url = Board.$container.data('create-column-url');
                Board.$container.append($empty_column);
                var $mask = IssuesFilters.add_waiting($empty_column);

                $.get(url)
                    .done(function(data) {
                        $empty_column.prepend(data);
                        $mask.addClass('no-spinner');
                        if (!$(':input:focus').length) {
                            $empty_column.find('.column-form input[type=text]').focus();
                        }
                    })
                    .fail(function() {
                        alert('Unable to retrieve the form to create a new column');
                        $empty_column.remove();
                    });

                return false;
            }, // on_add_click

            on_add_cancel_click: function() {
                $(this).closest('.board-column').remove();
            }, // on_add_cancel_click

            on_add_submit: function(ev) {
                return Board.arranger.on_submit.bind(this)(ev, Board.arranger.on_add_submit_done, 'create');
            }, // on_add_submit

            on_add_submit_done: function (data) {
                var $node = this.$form.closest('.board-column'),
                    $data = $(data),
                    key = $data.filter('.issues-list-container').data('key');

                $node.empty().removeClass('create-mode').append($data);
                $node.data('key', key);
                $node.attr('data-key', key);
            }, // on_add_submit_done

            subscribe_updates: function() {
                if (Board.mode != 'project') { return; }
                WS.subscribe(
                    'gim.front.Repository.' + main_repository_id + '.model.updated.is.Column',
                    'Board__arranger__on_update_column_alert',
                    Board.arranger.on_update_column_alert,
                    'prefix'
                );
                WS.subscribe(
                    'gim.front.Repository.' + main_repository_id + '.model.deleted.is.Column',
                    'Board__arranger__on_delete_column_alert',
                    Board.arranger.on_delete_column_alert,
                    'prefix'
                );

            }, // subscribe_updates

            can_update_column_on_alert: function(method, topic, args, kwargs) {
                if (typeof Board.arranger.updating_ids[kwargs.id] != 'undefined' || kwargs.front_uuid && UUID.exists(kwargs.front_uuid) && UUID.has_state(kwargs.front_uuid, 'waiting')) {
                    setTimeout(function() {
                        Board.arranger[method](topic, args, kwargs);
                    }, 100);
                    return false;
                }
                Board.arranger.updating_ids[kwargs.id] = true;
                return true;
            }, // can_update_column_on_alert

            on_update_column_alert: function(topic, args, kwargs) {
                if (!kwargs.model || kwargs.model != 'Column' || !kwargs.id || !kwargs.project_number) {
                    return;
                }

                if (Board.mode != 'project' || kwargs.project_number != Board.$container.data('key')) {
                    return;
                }

                if (!Board.arranger.can_update_column_on_alert('on_update_column_alert', topic, args, kwargs)) {
                    return;
                }

                // find the column
                var selector = '.board-column[data-key=' + kwargs.id + ']';
                if (kwargs.front_uuid) {
                    selector += ', .board-column[data-front-uuid=' + kwargs.front_uuid + ']';
                }
                var $node = Board.$container.find(selector),
                    done = false,
                    $to_delete, list_to_refresh;
                if ($node.length) {
                    // we found a column

                    if ($node.data('key') != kwargs.id || kwargs.is_new) {
                        // not the same id, but it's the same front-uuid
                        // it means it's a column freshly created and we'll update it
                        $to_delete = $node;
                        try {
                            // do we already have an list here?
                            list_to_refresh = $node.find('.issues-list-container')[0].IssuesList;
                            if (list_to_refresh) {
                                // yes, so we simply refresh it, and we're done
                                list_to_refresh.refresh();
                                $to_delete = null;
                                done = true;
                            }
                        } catch (e) {}
                    } else {
                        // the column exist, we just change its name and we're done
                        // we need to simulate capfirst as in the template
                        $node.find('.column-title').text(kwargs.name ? kwargs.name[0].toUpperCase() +  kwargs.name.substring(1) : '');
                        list_to_refresh = $node.find('.issues-list-container')[0].IssuesList;
                        list_to_refresh.$node.data('position', kwargs.position);
                        list_to_refresh.$node.attr('data-position', kwargs.position);
                        Board.arranger.ask_for_reorder();
                        done = true;
                    }
                }

                if (!done) {
                    // we have to get a new list

                    $.get(kwargs.url + (UrlParser.parse(kwargs.url).search ? '&' : '?') + 'with-icons=1')
                        .done(function(data) {
                            var $data = $(data),
                                $column = $('<div class="board-column"></div>'),
                                list, key;

                            if ($to_delete) {
                                $to_delete.remove();
                            }

                            Board.$container.append($column);
                            $column.append($data);
                            list = new IssuesList($column.find('.issues-list'));
                            key = list.$container_node.data('key');
                            $column.attr('data-key', key);
                            $column.data('key', key);
                            IssuesList.add_list(list);
                            Board.arranger.ask_for_reorder();

                        })
                        .fail(function() {
                            alert("An error occurred while loading a new column. Please refresh the whole page.")
                        })
                        .always(function() {
                            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                                UUID.set_state(kwargs.front_uuid, '');
                            }
                            delete Board.arranger.updating_ids[kwargs.id];
                        });

                } else {
                    if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                        UUID.set_state(kwargs.front_uuid, '');
                    }
                    delete Board.arranger.updating_ids[kwargs.id];
                }


            }, // on_update_column_alert

            on_delete_column_alert: function(topic, args, kwargs) {
                if (!kwargs.model || kwargs.model != 'Column' || !kwargs.id || !kwargs.project_number) {
                    return;
                }

                if (Board.mode != 'project' || kwargs.project_number != Board.$container.data('key')) {
                    return;
                }

                if (!Board.arranger.can_update_column_on_alert('on_delete_column_alert', topic, args, kwargs)) {
                    return;
                }

                // find the column
                var selector = '.board-column[data-key=' + kwargs.id + ']';
                if (kwargs.front_uuid) {
                    selector += ', .board-column[data-front-uuid=' + kwargs.front_uuid + ']';
                }
                var $node = Board.$container.find(selector);

                if ($node.length) {
                    try {
                        var list = $node.find('.issues-list')[0].IssuesList;
                        if (list) {
                            IssuesList.remove_list(list);
                        }
                    } catch (e) {}
                    $node.remove();
                    Board.arranger.ask_for_reorder();
                }

                if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                    UUID.set_state(kwargs.front_uuid, '');
                }
                delete Board.arranger.updating_ids[kwargs.id];

            }, // on_delete_column_alert

            init: function() {
                if (!Board.container) { return; }

                var $refresh_list_item = $('#issues-list-options-board-main').find('a.refresh-list').parent();
                if (Board.mode == 'project' && Board.editable) {
                    $refresh_list_item.after(
                        '<li><a href="#" class="add-column">Add a column</a></li>'
                    );

                    $document.on('click', '.board-column-edit', Board.arranger.on_edit_click);
                    $document.on('click', '.column-edit-form button.btn-cancel, .column-delete-form button.btn-cancel', Board.arranger.on_edit_or_delete_cancel_click);
                    $document.on('submit', '.column-edit-form', Board.arranger.on_edit_submit);

                    $document.on('click', '.column-edit-form .btn-delete', Board.arranger.on_delete_click);
                    $document.on('submit', '.column-delete-form', Board.arranger.on_delete_submit);

                    Board.filters.$options_node.on('click', '.add-column', Ev.stop_event_decorate_dropdown(Board.arranger.on_add_click));
                    $document.on('click', '.column-create-form button.btn-cancel', Board.arranger.on_add_cancel_click);
                    $document.on('submit', '.column-create-form', Board.arranger.on_add_submit);

                    $document.on('focus', '.column-form :input', function() {
                        PanelsSwapper.select_panel_from_node($(this).closest('.board-column').find('.issues-list-container'));
                    });
                }

                $refresh_list_item.after(
                    '<li><a href="#" class="restore-closed-lists">Restore hidden columns</a></li>'
                );
                if (!Board.$columns.length) { return; }
                Board.filters.$options_node.on('click', '.restore-closed-lists', Ev.stop_event_decorate_dropdown(Board.arranger.restore_hidden));

                Board.arranger.prepare_sortable();

                Board.arranger.subscribe_updates();
            } // init

        }, // Board.arranger

        lists: {
            lists_selector: '.issues-list-container',
            filters_selector: '.issues-filters',
            loading: false,
            asked_scroll_to: {},

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
                var $columns = Board.$columns.not('.hidden, .loaded, .loading'),
                    container_left = Board.container.scrollLeft,
                    container_right = container_left + Board.container.offsetWidth;
                for (var i = 0; i < $columns.length; i++) {
                    var column = $columns[i], $column, $issues_list_node, $filters_node, url;

                    if (!Board.lists.is_column_visible(column, container_left, container_right)) { continue; }

                    $column = $(column);
                    $issues_list_node = $column.children(Board.lists.lists_selector);
                    $filters_node = $column.children(Board.lists.filters_selector);
                    url = $issues_list_node.children('.issues-list').data('url');
                    $column.addClass('loading');

                    IssuesFilters.reload_filters_and_list(url, $filters_node, $issues_list_node, true);
                }
                Board.lists.loading = false;

            }, // load_visible

            on_closer_click: function () {
                var $this = $(this),
                    $column = $this.parents('.board-column');
                Board.arranger.hide_column($column);
                $column.removeClass('mini');
                return false;
            }, // on_closer_click

            on_minifier_click: function () {
                $(this).parents('.board-column').addClass('mini');
                Board.arranger.on_columns_rearranged();
                return false;
            },

            on_unminifier_click: function () {
                $(this).parents('.board-column').removeClass('mini');
                Board.arranger.on_columns_rearranged();
                return false;
            },

            animate_scroll_to: function() {
                if (!Board.lists.asked_scroll_to.running) { return; }
                Board.lists.asked_scroll_to.currentTime += Board.lists.asked_scroll_to.increment;
                Board.container.scrollLeft = Math.easeInOutQuad(
                    Board.lists.asked_scroll_to.currentTime,
                    Board.lists.asked_scroll_to.start,
                    Board.lists.asked_scroll_to.change,
                    Board.lists.asked_scroll_to.duration
                );
                if (Board.lists.asked_scroll_to.currentTime < Board.lists.asked_scroll_to.duration) {
                    requestNextAnimationFrame(Board.lists.animate_scroll_to);
                } else {
                    Board.lists.asked_scroll_to.running = false;
                }
            },

            scroll_to: function (position) {
                if (position === null) {
                    Board.lists.asked_scroll_to.running = false;
                    return;
                }
                if (position < 0) {
                    position = 0;
                } else if (position > Board.dimensions.scrollLeftMax) {
                    position = Board.dimensions.scrollLeftMax;
                }
                var already_running = Board.lists.asked_scroll_to.running,
                    start = Board.container.scrollLeft;

                Board.lists.asked_scroll_to = {
                    start: start,
                    change: position - start,
                    currentTime: 0,
                    increment: 20,
                    duration: 500,
                    running: true
                };

                if (!already_running) {
                    requestNextAnimationFrame(Board.lists.animate_scroll_to);
                }
            }, // scroll_to

            init: function() {
                if (!Board.$columns.length) { return; }
                $document.on('reloaded', IssuesList.container_selector, Board.dragger.on_column_loaded);
                $document.on('reloaded', IssuesList.container_selector, Board.arranger.on_column_loaded);
                $document.on('reloaded', IssuesList.container_selector, Board.filters.on_column_loaded);
                Board.lists.load_visible();
                $('.board-column-closer').on('click', Ev.stop_event_decorate(Board.lists.on_closer_click));
                $('.board-column-minifier').on('click', Ev.stop_event_decorate(Board.lists.on_minifier_click));
                $('.board-column-unminifier').on('click', Ev.stop_event_decorate(Board.lists.on_unminifier_click));
                jwerty.key('x', IssuesList.on_current_list_key_event('close'));

            } // init

        }, // Board.lists

        dragger: {
            activated: false,
            all_selector: '.board-column.loaded .issues-group:not(.template) .issues-group-issues',
            active_selector: '.board-column.loaded:not(.hidden) .issues-group:not(.template) .issues-group-issues',
            dragging: false,
            updating: false,
            $hidden_duplicates: [],

            on_drag_start: function(ev, ui) {
                Board.dragger.dragging = true;

                var sortable_node = this,
                    ui_item = ui.item,
                    ui_helper = ui.helper,
                    ui_placeholder = ui.placeholder;

                Board.dragger.check_issue_movable(sortable_node, ui_item);

                ui_helper.addClass('force-without-details');

                requestNextAnimationFrame(function() {
                    if (!Board.dragger.dragging) { return; }

                    Board.$container.addClass('dragging');
                    var $list_node = ui_item.closest('.issues-list'),
                        list_without_details = $list_node.hasClass('without-details'),
                        item_details_toggled = ui_item.hasClass('details-toggled'),
                        without_details = list_without_details && !item_details_toggled || item_details_toggled,
                        sortable = $(sortable_node).data('ui-sortable');

                    ui_item.removeClass('recent');
                    ui_helper.removeClass('recent');
                    ui_placeholder.removeClass('recent');

                    if (!without_details) {
                        ui_helper.removeClass('force-without-details');
                    }
                    ui_helper.width(ui_placeholder.width());
                    ui_helper.height(ui_placeholder.height());

                    // we may have the same item in may columns (for labels for example)
                    Board.dragger.$hidden_duplicates = $('.board-column #' + ui_item[0].id + ':not(.ui-sortable-placeholder):not(.ui-sortable-helper)').not(ui_item[0]);
                    if (Board.dragger.$hidden_duplicates.length) {
                        Board.dragger.$hidden_duplicates.hide();
                    }

                    sortable._cacheHelperProportions();
                    sortable._preserveHelperProportions = true;
                    sortable._setContainment();


                    Board.dragger.show_empty_columns();
                    sortable.refreshPositions();
                });
            }, // on_drag_start

            on_drag_stop: function(ev, ui) {
                Board.dragger.dragging = false;

                for (var i = 0; i < Board.dragger.$hidden_duplicates.length; i++) {
                    var $item = $(Board.dragger.$hidden_duplicates[i]);
                    // the item may have been removed so we check
                    if ($item.closest(document.documentElement).length) {
                        $item.show();
                    }
                }
                Board.dragger.$hidden_duplicates = [];

                Board.$container.removeClass('dragging');
                ui.item.removeClass('force-without-details');

                Board.dragger.hide_empty_columns();
                requestNextAnimationFrame(function() { Board.dragger.update_sortables()});

            }, // on_drag_stop

            prepare_list_if_empty: function(list) {
                if (!list.$node.has('.issues-group:not(.template)').length) {
                    var group = list.create_group(null, null, null);
                    group.$node.addClass('empty-sortable');
                    group.list.create_empty_node();
                    group.list.$empty_node.show();
                    group.$count_node.text(0);
                    group.$issues_node.addClass('in');
                    group.collapsed = false;
                    group.list.groups = [];  // we don't count it in groups to avoid navigating in it
                }
            }, // prepare_list_if_empty

            show_empty_columns: function () {
                $('.issues-group.empty-sortable:not(.visible)').addClass('visible').siblings('.no-issues').hide();
            }, // show_empty_columns

            hide_empty_columns: function () {
                $('.issues-group.empty-sortable.visible').not(':has(.issue-item)').removeClass('visible').siblings('.no-issues').show();
            }, // hide_empty_columns

            on_column_loaded: function () {
                if (!Board.dragger.activated) { return; }
                var $list_container_node = $(this);
                requestNextAnimationFrame(function() {
                    var list = IssuesList.get_for_node($list_container_node),
                        not_loaded = list.$node.hasClass('not-loaded');

                    if (!not_loaded) {
                        Board.dragger.prepare_list_if_empty(list);
                    }

                    Board.dragger.update_sortables(true);
                });
            }, // on_column_loaded

            on_columns_rearranged: function() {
                if (!Board.dragger.activated) { return; }
                requestNextAnimationFrame(function() {
                    Board.dragger.update_sortables(true);
                });
            }, // on_columns_rearranged

            on_sortable_create: function(ev, ui) {
                var obj = $(this).data('ui-sortable');
                obj._mouseDrag = Board.dragger._sortable_override_mouse_drag;

                obj._oldRemoveCurrentsFromItems = obj._removeCurrentsFromItems;
                obj._removeCurrentsFromItems = Board.dragger._sortable_override__removeCurrentsFromItems;

                obj._oldRearrange = obj._rearrange;
                obj._rearrange = Board.dragger._sortable_override_rearrange;
            }, // on_sortable_create

            _sortable_override__removeCurrentsFromItems: function () {
                this._oldRemoveCurrentsFromItems();
                if (!this.canMoveInsideSelf) {
                    // we remove the other items in the same list to disallow dragging on this list
                    // (we keep a sibling to be able to drag it to the same place)
                    var currentItem = this.currentItem[0],
                        issue = currentItem.IssuesListIssue,
                        index=issue.group.filtered_issues.indexOf(issue),
                        siblingPosition =  issue.group.filtered_issues[index+1] ? 1 : (issue.group.filtered_issues[index-1] ? -1 : null),
                        sibling = siblingPosition ? issue.group.filtered_issues[index + siblingPosition] : null;
                    if (siblingPosition) {
                        this.currentItemSibling = sibling.$node[0];
                        this.currentItemSiblingDirection = siblingPosition;
                    } else {
                        this.currentItemSibling = null;
                    }
                    this.items = this.items.filter(function(item) {
                        return (
                            item.item[0].IssuesListIssue.group.list != issue.group.list
                            ||
                            item.item[0] == currentItem
                            ||
                            (sibling && item.item[0].IssuesListIssue == sibling)
                        );
                    });
                }
            }, // _sortable_override__removeCurrentsFromItems

            _sortable_override_rearrange: function(event, i, a, hardRefresh) {
                if (!this.canMoveInsideSelf && this.currentItemSibling && i && i.item && i.item.length && i.item[0] == this.currentItemSibling) {
                    // We force the item to be back at its original position
                    this.direction = this.currentItemSiblingDirection == 1 ? 'down' : 'up';
                }
                this._oldRearrange(event, i, a, hardRefresh);
            }, // _sortable_override_rearrange

            _sortable_override_mouse_drag: function (event) {
                // copy of _mouseDrag from jqueryUI.sortable, to not scroll more than the max of the board
                // see `CHANGED HERE` parts
                var i, item, itemElement, intersection,
                    o = this.options,
                    scrolled = false;

                //Compute the helpers position
                this.position = this._generatePosition(event);
                // CHANGED HERE: we don't want the helper to overflow on the right
                this.position.left = Math.min(this.position.left, Board.dimensions.scrollWidth - this.helperProportions.width);

                this.positionAbs = this._convertPositionTo("absolute");

                if (!this.lastPositionAbs) {
                    this.lastPositionAbs = this.positionAbs;
                }

                //Do scrolling
                if(this.options.scroll) {
                    if(this.scrollParent[0] !== this.document[0] && this.scrollParent[0].tagName !== "HTML") {

                        if((this.overflowOffset.top + this.scrollParent[0].offsetHeight) - event.pageY < o.scrollSensitivity) {
                            this.scrollParent[0].scrollTop = scrolled = this.scrollParent[0].scrollTop + o.scrollSpeed;
                        } else if(event.pageY - this.overflowOffset.top < o.scrollSensitivity) {
                            this.scrollParent[0].scrollTop = scrolled = this.scrollParent[0].scrollTop - o.scrollSpeed;
                        }

                        // CHANGED HERE: added max with Board.dimensions.scrollLeftMax
                        if((this.overflowOffset.left + this.scrollParent[0].offsetWidth) - event.pageX < o.scrollSensitivity) {
                            this.scrollParent[0].scrollLeft = scrolled = Math.min(this.scrollParent[0].scrollLeft + o.scrollSpeed, Board.dimensions.scrollLeftMax);
                        } else if(event.pageX - this.overflowOffset.left < o.scrollSensitivity) {
                            this.scrollParent[0].scrollLeft = scrolled = Math.min(this.scrollParent[0].scrollLeft - o.scrollSpeed, Board.dimensions.scrollLeftMax);
                        }

                    } else {

                        if(event.pageY - this.document.scrollTop() < o.scrollSensitivity) {
                            scrolled = this.document.scrollTop(this.document.scrollTop() - o.scrollSpeed);
                        } else if(this.window.height() - (event.pageY - this.document.scrollTop()) < o.scrollSensitivity) {
                            scrolled = this.document.scrollTop(this.document.scrollTop() + o.scrollSpeed);
                        }

                        if(event.pageX - this.document.scrollLeft() < o.scrollSensitivity) {
                            scrolled = this.document.scrollLeft(this.document.scrollLeft() - o.scrollSpeed);
                        } else if(this.window.width() - (event.pageX - this.document.scrollLeft()) < o.scrollSensitivity) {
                            scrolled = this.document.scrollLeft(this.document.scrollLeft() + o.scrollSpeed);
                        }

                    }

                    if(scrolled !== false && $.ui.ddmanager && !o.dropBehaviour) {
                        $.ui.ddmanager.prepareOffsets(this, event);
                    }
                }

                //Regenerate the absolute position used for position checks
                this.positionAbs = this._convertPositionTo("absolute");

                //Set the helper position
                if(!this.options.axis || this.options.axis !== "y") {
                    this.helper[0].style.left = this.position.left+"px";
                }
                if(!this.options.axis || this.options.axis !== "x") {
                    this.helper[0].style.top = this.position.top+"px";
                }

                //Rearrange
                for (i = this.items.length - 1; i >= 0; i--) {

                    //Cache variables and intersection, continue if no intersection
                    item = this.items[i];
                    itemElement = item.item[0];
                    intersection = this._intersectsWithPointer(item);
                    if (!intersection) {
                        continue;
                    }

                    // Only put the placeholder inside the current Container, skip all
                    // items from other containers. This works because when moving
                    // an item from one container to another the
                    // currentContainer is switched before the placeholder is moved.
                    //
                    // Without this, moving items in "sub-sortables" can cause
                    // the placeholder to jitter between the outer and inner container.
                    if (item.instance !== this.currentContainer) {
                        continue;
                    }

                    // cannot intersect with itself
                    // no useless actions that have been done before
                    // no action if the item moved is the parent of the item checked
                    if (itemElement !== this.currentItem[0] &&
                        this.placeholder[intersection === 1 ? "next" : "prev"]()[0] !== itemElement &&
                        !$.contains(this.placeholder[0], itemElement) &&
                        (this.options.type === "semi-dynamic" ? !$.contains(this.element[0], itemElement) : true)
                    ) {

                        this.direction = intersection === 1 ? "down" : "up";

                        if (this.options.tolerance === "pointer" || this._intersectsWithSides(item)) {
                            this._rearrange(event, item);
                        } else {
                            break;
                        }

                        this._trigger("change", event, this._uiHash());
                        break;
                    }
                }

                //Post events to containers
                this._contactContainers(event);

                //Interconnect with droppables
                if($.ui.ddmanager) {
                    $.ui.ddmanager.drag(this, event);
                }

                //Call callbacks
                this._trigger("sort", event, this._uiHash());

                this.lastPositionAbs = this.positionAbs;
                return false;

            }, // _sortable_override_mouse_drag

            create_placeholder: function(currentItem) {
                return currentItem.clone().addClass('ui-sortable-placeholder').append('<div class="mask"/>').show();
            }, // create_placeholder

            on_drag_update: function(ev, ui) {
                var $new_group = ui.item.parent(),
                    new_group, issue;

                if (this !== $new_group[0]) {
                    // this is called for the source and receiver, but we only need to work on the receiver
                    return;
                }

                $new_group = $new_group.parent();
                new_group = $new_group[0].IssuesListGroup;
                issue = ui.item[0].IssuesListIssue;

                requestNextAnimationFrame(function() {
                    // a list can handle positions only when filtered on a project, sorted by card position, without group-by
                    // so in this case we know we only have one group in this list
                    var old_group = issue.group,
                        group_changed = new_group != old_group,
                        old_list = old_group.list,
                        new_list = new_group.list,
                        was_current_issue = old_group.current_issue == issue,
                        old_list_can_handle_positions = old_list.$node.data('can-handle-positions'),
                        new_list_can_handle_positions = new_list.$node.data('can-handle-positions'),
                        handle_positions = old_list_can_handle_positions || new_list_can_handle_positions,
                        $duplicates, project_number, is_asc, sibling_issue, old_position = -1, new_position = -1, i, pp, filter;

                    if (group_changed) {
                        if ($new_group.hasClass('empty-sortable')) {
                            $new_group.removeClass('empty-sortable visible');
                            new_list.groups.push(new_group);
                        }

                        if (was_current_issue) {
                            issue.unset_current();
                        }

                        // remove the existing duplicate(s)
                        $duplicates = new_list.$node.find('#issue-' + issue.id + '.issue-item:not(.ui-sortable-placeholder):not(.ui-sortable-helper)').not(issue.$node);
                        for (var i = 0; i < $duplicates.length; i++) {
                            $duplicates[i].IssuesListIssue.clean();
                        }

                        issue.group = new_group;
                    }

                    // passing `true` for `dont_reorder` as we'll do it later
                    if (group_changed) {
                        old_group.update_issues_list(true);
                    }
                    new_group.update_issues_list(true);


                    if (group_changed && was_current_issue) {
                        issue.set_current();
                    }

                    if (handle_positions) {
                        // we assume we are in the column of a project (old_group and new_group are project column (or issues not in the project)
                        project_number = new_list.filtered_project_number || old_list.filtered_project_number;

                        pp = issue.project_positions;
                        if (old_list_can_handle_positions && pp[project_number] && pp[project_number].card_position) {
                            old_position = pp[project_number].card_position;
                        }

                        if (new_list_can_handle_positions) {
                            // get the reference issue in the new group
                            is_asc = new_list.sort_direction == 'asc';
                            sibling_issue = new_group[ is_asc ? 'get_previous_issue' : 'get_next_issue'](true, issue);

                            // place our issue after the reference issue, or at first if none
                            if (sibling_issue) {
                                new_position = sibling_issue.project_positions[project_number].card_position + 1;
                            } else {
                                sibling_issue = new_group[ is_asc ? 'get_next_issue' : 'get_previous_issue'](true, issue);
                                if (sibling_issue) {
                                    new_position = sibling_issue.project_positions[project_number].card_position;
                                } else {
                                    new_position = 1;
                                }
                            }
                            if (!group_changed && old_position < new_position) {
                                new_position -= 1;
                            }
                        }

                        // decrement positions for ones with higher position in old group
                        // we do it after getting the position in the new group as both group may be the same
                        if (old_list_can_handle_positions && old_position != -1) {
                            for (i = 0; i < old_group.issues.length; i++) {
                                pp = old_group.issues[i].project_positions;
                                if (pp[project_number] && pp[project_number].card_position && pp[project_number].card_position >= old_position) {
                                    pp[project_number].card_position -= 1;
                                }
                            }
                        }

                        // increment positions for ones with higher position in new group
                        if (new_list_can_handle_positions && new_position != -1) {
                            for (i = 0; i < new_group.issues.length; i++) {
                                if (new_group.issues[i] === issue) { continue; }
                                pp = new_group.issues[i].project_positions;
                                if (pp[project_number] && pp[project_number].card_position && pp[project_number].card_position >= new_position) {
                                    pp[project_number].card_position += 1;
                                }
                            }
                            // and save our position
                            issue.move_to_project_column(project_number, parseInt(new_list.$container_node.data('key'), 10), new_position);
                        }

                        if (old_list_can_handle_positions && !new_list_can_handle_positions) {
                            // we moved the issue from a project column to the column "not in the project"
                            issue.remove_from_project(project_number);
                        }

                    } // if (handle_positions)

                    // do we have to put the issue in another group on the same list
                    if (!new_list_can_handle_positions && group_changed && new_list.group_by_key) {
                        filter = issue.get_filter_for(new_list.group_by_key);
                        new_group = new_list.get_group_for_value(filter.value) || new_list.create_group(filter.value, filter.text, filter.description);
                        if (new_group != issue.group) {
                            new_list.change_issue_group(issue, new_group);
                        }
                    }

                    // we can now reorder
                    if (group_changed && old_group.issues.length) {
                        old_group.ask_for_reorder();
                    }
                    new_group.ask_for_reorder();

                    if (group_changed || handle_positions && new_position != old_position) {
                        Board.dragger.remote_move_issue(issue, old_list, new_list, new_position && new_position > 0 ? new_position : null);
                    }

                    if (group_changed && !old_group.issues.length) {
                        old_list.remove_group(old_group);
                    }
                });
            }, // on_drag_receive

            remote_move_issue: function(issue, old_list, new_list, position) {
                var new_key = new_list.$container_node.data('key'),
                    url = old_list.base_url + 'move/' + issue.number + '/to/' + new_key + '/',
                    front_uuid = UUID.generate('waiting'),
                    data = {csrfmiddlewaretoken: $body.data('csrf'), front_uuid: front_uuid},
                    context = {
                        old_list: old_list,
                        new_list: new_list,
                        issue: issue,
                        position: position
                    };
                if (position) { data.position = position; }
                $.post(url, data)
                    .fail($.proxy(Board.dragger.on_remote_move_issue_failure, context))
                    .always(function() {UUID.set_state(front_uuid, '');});
            }, // remote_move_issue

            on_remote_move_issue_failure: function(xhr, data) {
                var context = this,
                    $message = $('<span/>').text("We couldn't update the issue ");
                $message.append($('<span style="font-weight: bold"/>').text(this.issue.$node.find('.issue-link').text()));
                $message.append($('<br/>'), $('<span/>').text('The related lists will be auto-reloaded in 5 seconds'));
                MessagesManager.add_messages([MessagesManager.make_message($message, 'error')]);
                setTimeout(function() {
                    context.old_list.refresh();
                    if (context.new_list != context.old_list) {
                        context.new_list.refresh();
                    }
                }, 5000);
            }, // on_remote_move_issue_failure

            check_issue_movable: function(sortable_node, ui_item) {
                requestNextAnimationFrame(function() {
                    var $list_node = ui_item.closest('.issues-list'),
                        list = $list_node[0].IssuesList,
                        issue = ui_item[0].IssuesListIssue,
                        url = list.base_url + 'can_move/' + issue.number + '/',
                        data = {csrfmiddlewaretoken: $body.data('csrf')},
                        context = {
                            sortable_node: sortable_node,
                            ui_item: ui_item
                        };
                $.post(url, data)
                    .fail($.proxy(Board.dragger.on_check_issue_movable_failure, context))
                });
            }, // check_issue_movable

            on_check_issue_movable_failure: function(xhr, data) {
                $(this.sortable_node).sortable('cancel');
                var ui_item = this.ui_item;
                setTimeout(function() {
                    Board.dragger.on_drag_stop({}, {item: ui_item});
                }, 10);
            }, // on_check_issue_movable_failure

            update_sortables: function(force_refresh) {
                if (Board.dragger.updating) {
                    requestNextAnimationFrame(Board.dragger.update_sortables);
                }
                Board.dragger.updating = true;
                var $lists = $(Board.dragger.all_selector),
                    refresh_needed = force_refresh, to_refresh = [];

                if (Board.dragger.dragging) {
                    Board.dragger.show_empty_columns();
                }

                for (var i = 0; i < $lists.length; i++) {
                    var $list = $($lists[i]),
                        sortable = $list.data('ui-sortable');

                    if (sortable) {
                        if (sortable.board_column.hasClass('hidden') || sortable.board_column.hasClass('not-loaded')) {
                            if (!sortable.options.disabled) {
                                $list.sortable('disable');
                                refresh_needed = true;
                            }
                        } else {
                            if (sortable.options.disabled) {
                                $list.sortable('enable');
                                refresh_needed = true;
                            }
                            to_refresh.push($list);
                        }
                        continue;
                    }

                    var $column = $list.closest('.board-column');
                    if ($column.hasClass('hidden') || $column.hasClass('not-loaded')) {
                        continue;
                    }
                    refresh_needed = true;
                    $list.sortable({
                        helper: 'clone',
                        appendTo: Board.$container,
                        // items: '> li.issue-item:not(.hidden)',
                        connectWith: Board.dragger.active_selector,
                        placeholder: {
                            element: Board.dragger.create_placeholder,
                            update: $.noop
                        },
                        containment: Board.container_selector,
                        scroll: true,
                        scrollSensitivity: 50,
                        scrollSpeed: 50,
                        cursor: 'move',
                        cursorAt: {
                            left: 5,
                            top: 5
                        },
                        distance: 0.5,
                        tolerance: 'pointer',
                        create: Board.dragger.on_sortable_create,
                        start: Board.dragger.on_drag_start,
                        stop: Board.dragger.on_drag_stop,
                        update: Board.dragger.on_drag_update
                    }).disableSelection();

                    $list.data('ui-sortable').board_column = $column;
                    $list.data('ui-sortable').canMoveInsideSelf = $list[0].parentNode.IssuesListGroup.list.$node.data('can-handle-positions');
                }

                if (refresh_needed) {
                    for (var j = 0; j < to_refresh.length; j++) {
                        to_refresh[j].sortable('refresh');
                    }
                }

                Board.dragger.updating = false;
            }, // update_sortables

            init: function() {
                if (!Board.$columns.length) { return; }
                Board.dragger.activated = true;
                // setTimeout(function() {
                //     MessagesManager.add_messages([MessagesManager.make_message(
                //         "Vertical position will only be saved on project columns ordered by card position, without group-by.",
                //     'info')]);
                // }, 2000);
            }
        }, // Board.dragger

        filters: {
            filters_selector: '#issues-filters-board-main',
            options_selector: '#issues-list-options-board-main',
            $options_node: null,
            quicksearch_selector: '#issues-list-search-board-main',
            $search_input: null,
            last_search: '',

            on_filter_or_option_click: function() {
                return Board.filters.reload_filters_and_lists(this.href);
            }, // on_filter_click

            reload_filters_and_lists: function(url, no_history) {
                $.get(url)
                    .done($.proxy(Board.filters.on_filters_loaded, {no_history: no_history, url: url}))
                    .fail(function() { window.location.href = url; });

                IssuesFilters.add_waiting($(Board.filters.filters_selector));
                IssuesFilters.add_waiting(Board.filters. $options_node);

                var $columns = Board.$columns,
                    querystring = UrlParser.parse(url).search;

                for (var i = 0; i < $columns.length; i++) {
                    var $column = $($columns[i]),
                        $issues_list_node = $column.children(Board.lists.lists_selector),
                        $issues_list = $issues_list_node.children('.issues-list'),
                        column_url = $issues_list.data('base-url') + querystring,
                        $filters_node;

                    $issues_list.data('url', column_url);

                    if ($column.hasClass('loaded')) {
                        $filters_node = $column.children(Board.lists.filters_selector);
                        IssuesFilters.reload_filters_and_list(column_url, $filters_node, $issues_list_node, true);
                    }

                }

                return false;
            }, // reload_filters_and_lists

            on_filters_loaded: function (data) {
                var $data = $(data),
                    $new_filters_node = $data.filter(Board.filters.filters_selector),
                    $new_options_node = $data.filter(Board.filters.options_selector);

                $new_filters_node.find('.deferrable').deferrable();
                $new_options_node.find('.deferrable').deferrable();
                $(Board.filters.filters_selector).replaceWith($new_filters_node);

                Board.filters.$options_node.find('li.dropdown-sort').replaceWith($new_options_node.find('li.dropdown-sort'));
                Board.filters.$options_node.find('li.dropdown-groupby').replaceWith($new_options_node.find('li.dropdown-groupby'));
                Board.filters.$options_node.find('li.dropdown-options').replaceWith($new_options_node.find('li.dropdown-options'));
                IssuesFilters.remove_waiting(Board.filters. $options_node);

                if (!this.no_history) {
                    Board.filters.add_history(this.url);
                }

            }, // on_filters_loaded

            add_history: function(url, replace) {
                if (window.history && window.history.pushState) {
                    window.history[replace ? 'replaceState' : 'pushState']({
                        type: 'BoardFilters',
                        body_id: body_id,
                        main_repository_id: main_repository_id,
                        filters_url: url
                    }, $document.attr('title'), url);
                }
            }, // add_history

            on_history_pop_state: function  (state) {
                if (state.body_id != body_id || state.main_repository_id != main_repository_id) {
                    return false;
                }
                Board.filters.reload_filters_and_lists(state.filters_url, true);
                return true;
            }, // on_history_pop_state

            on_search: function() {
                var loaded_lists = IssuesList.get_loaded_lists();
                Board.filters.last_search = Board.filters.$seach_input.val();
                for (var i = 0; i < loaded_lists.length; i++) {
                    Board.filters.update_list_search(loaded_lists[i]);
                }
            }, // on_search

            update_list_search: function(list) {
                list.skip_on_filter_done_once = true;
                list.$search_input.one('quicksearch.refresh', $.proxy(Board.filters.on_list_filter_done, list));
                list.$search_input.val(Board.filters.last_search);
                list.$search_input.trigger('quicksearch.refresh');
            }, // update_list_search

            on_list_filter_done: function() {
                // `this` is the list object
                for (var i = 0; i < this.groups.length; i++) {
                    var group = this.groups[i];
                    group.update_filtered_issues();
                }
            }, // on_list_filter_done

            on_column_loaded: function () {
                Board.filters.update_list_search(this.IssuesList);
            }, // on_column_loaded

            init: function() {
                if (!Board.$columns.length) { return; }
                Board.filters.$seach_input = $(Board.filters.quicksearch_selector + ' input');
                Board.filters.$options_node = $(Board.filters.options_selector);

                $document.on('click', Board.filters.filters_selector + ' a:not(.accordion-toggle):not(.filters-toggler)', Ev.stop_event_decorate(Board.filters.on_filter_or_option_click));

                Board.filters.$options_node.on('click', '.dropdown-sort ul a, .dropdown-groupby ul a, .dropdown-metric ul a',  Ev.stop_event_decorate_dropdown(Board.filters.on_filter_or_option_click));

                Board.filters.$options_node.on('click', '.toggle-issues-details', Ev.stop_event_decorate_dropdown(IssuesList.toggle_details));
                Board.filters.$options_node.on('click', '.refresh-list', Ev.stop_event_decorate_dropdown(IssuesList.refresh));
                Board.filters.$options_node.on('click', '.close-all-groups', Ev.stop_event_decorate_dropdown(IssuesList.close_all_groups));
                Board.filters.$options_node.on('click', '.open-all-groups', Ev.stop_event_decorate_dropdown(IssuesList.open_all_groups));

                $document.on('click', Board.filters.quicksearch_selector, Ev.cancel);
                $document.on('quicksearch.after', Board.filters.quicksearch_selector, Board.filters.on_search);
                $document.on('focus', '.issues-list-search-main-board-trigger', Ev.set_focus(function () { return Board.filters.$seach_input; }, 200));

                Board.filters.add_history(window.location.href, true);
                window.HistoryManager.callbacks['BoardFilters'] = Board.filters.on_history_pop_state;
        } // init

        }, // Board.filters

        project_editor: {
            $modal: $('#project-editor'),
            $modal_header: null,
            $modal_body: null,
            $modal_footer: null,
            create_mode: false,
            updating_ids: {},

            exit_edit_mode: function() {
                if (Board.project_editor.create_mode) {
                    Board.project_editor.$modal.modal('hide');
                } else {
                    Board.project_editor.$modal.removeClass('edit-mode');
                    Board.project_editor.$modal_body.empty().append(
                        '<em>Loading project information <i class="fa fa-spinner fa-spin"> </i></em>'
                    );
                    Board.project_editor.$modal_footer.empty();
                    Board.project_editor.load_summary();
                }
            }, // exit_edit_mode

            load_summary: function() {
                $.get(Board.project_editor.$modal.data('summary-url'))
                    .done(Board.project_editor.on_summary_loaded)
                    .fail(Board.project_editor.on_summary_load_failed);
            }, // load_summary

            on_summary_loaded: function(data) {
                var $data = $(data);
                Board.project_editor.$modal_header.empty().append($data.find('.modal-header').children());
                Board.project_editor.$modal_body.empty().append($data.find('.modal-body').children());
                Board.project_editor.$modal_footer.empty().append($data.find('.modal-footer').children());
            }, // on_summary_loaded

            on_summary_load_failed: function(xhr, data) {
                Board.project_editor.$modal_body.empty().append(
                    '<div class="alert alert-error">We were unable to load the project information</div>'
                );
                Board.project_editor.$modal_footer.empty().append(
                    '<div class="row-fluid align-right"><div class="span12"><button class="btn btn-blue btn-loading">Retry <i class="fa fa-spinner fa-spin"> </i></button></div></div>'
                );
                Board.project_editor.$modal_footer.find('.btn').on('click', function() {
                    $(this).addClass('loading');
                    Board.project_editor.load_summary();
                });
            }, // on_summary_load_failed

            disable_form: function($form) {
                Board.project_editor.$modal_footer.find(':button').prop('disabled', true);
                FormTools.disable_form($form);
            }, // disable_form

            enable_form: function($form) {
                FormTools.enable_form($form);
                Board.project_editor.$modal_footer.find(':button').prop('disabled', false);
            }, // enable_form

            handle_form: function($form, ev, front_uuid) {
                return FormTools.handle_form($form, ev, front_uuid, Board.project_editor.disable_form);
            }, // handle_form

            on_submit: function(ev, on_submit_done, action_name) {
                var $form = $(this), context;
                if ($form.data('disabled')) { return false; }

                context = Board.project_editor.handle_form($form, ev);
                if (context === false) { return false; }

                Board.project_editor.$modal.find('.alert').remove();

                context.action_name = action_name;

                var data, action;

                if (action_name == 'delete') {

                    Board.project_editor.$modal_footer.find('.btn-delete').addClass('loading');
                    Board.project_editor.action_on_delete_popover('hide');

                    data = [{name: 'csrfmiddlewaretoken', value: $form[0].csrfmiddlewaretoken.value}];
                    action = $form.data('delete-url');

                } else {

                    Board.project_editor.$modal_footer.find('button.submit').addClass('loading');

                    var $input = $form.find('input[name=name]');
                    if ($input.length && !$input.val().trim()) {
                        $input.after('<div class="alert alert-error">You must enter a name</div>');
                        Board.project_editor.$modal_footer.find('button.submit').removeClass('loading');
                        Board.project_editor.enable_form($form);
                        $input.focus();
                        FormTools.move_cursor_at_the_end($input);
                        return false;
                    }

                }

                Board.project_editor.$modal[0].setAttribute('data-front-uuid', context.uuid);

                FormTools.post_form_with_uuid($form, context,
                    on_submit_done,
                    Board.project_editor.on_submit_failed,
                    data, action
                );
            }, // on_submit

            on_confirm_deletion: function(ev) {
                var $form = Board.project_editor.$modal_body.find('form');
                $.proxy(Board.project_editor.on_submit, $form[0])(ev,
                    Board.project_editor.on_delete_submit_done,
                    'delete'
                )
            }, // on_confirm_deletion

            on_submit_failed: function(xhr, data) {
                Board.project_editor.enable_form(this.$form);
                var msg = 'The project cannot be ' + this.action_name + 'd for now. Please retry in a few seconds';
                Board.project_editor.$modal_body.append('<div class="alert alert-error">' + msg + '</div>');
                Board.project_editor.$modal_footer.find('button.loading').removeClass('loading');
                if (this.action_name != 'delete') {
                    var $input = this.$form.find('input[name=name]');
                    $input.focus();
                    FormTools.move_cursor_at_the_end($input);
                }
            }, // on_submit_failed

            on_edit_click: function() {
                $(this).addClass('loading');
                $.get(Board.project_editor.$modal.data('edit-url'))
                    .done(Board.project_editor.on_edit_loaded)
                    .fail(Board.project_editor.on_edit_load_failed);
            }, // on_edit_click

            on_edit_loaded: function(data) {
                var $data = $(data),
                    $edit_buttons = $data.find('.edit-buttons'),
                    $input;

                $edit_buttons.remove();

                Board.project_editor.$modal.addClass('edit-mode');
                Board.project_editor.$modal_body.empty().append($data);
                Board.project_editor.$modal_footer.empty().append($edit_buttons);
                Board.project_editor.action_on_delete_popover();  // init

                $input =  Board.project_editor.$modal_body.find('input[name=name]');
                $input.focus();
                FormTools.move_cursor_at_the_end($input);
            }, // on_edit_loaded

            on_edit_load_failed: function(xhr, data) {
                Board.project_editor.exit_edit_mode();
                if (xhr.status != 409) {
                    // 409 Conflict Indicates that the request could not be processed because of
                    // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                    alert('Unable to retrieve the form to edit this project');
                }
            }, // on_edit_load_failed

            on_edit_submit_click: function() {
                Board.project_editor.$modal_body.find('form').trigger('submit');
            }, // on_edit_submit_click

            on_edit_submit: function(ev) {
                return Board.project_editor.on_submit.bind(this)(ev, Board.project_editor.on_edit_submit_done, 'update');

            }, // on_edit_submit

            on_edit_submit_done: function(data) {
                if (data.indexOf('<form') == 0) {
                    $.proxy(Board.project_editor.on_submit_failed, this)({}, data);
                    return;
                }
                Board.project_editor.on_summary_loaded($(data));
            }, // on_edit_submit_done

            on_create_submit: function(ev) {
                return Board.project_editor.on_submit.bind(this)(ev, Board.project_editor.on_create_submit_done, 'create');
            }, // on_create_submit

            on_create_submit_done: function(data) {
                if (data.indexOf('<form') == 0) {
                    $.proxy(Board.project_editor.on_submit_failed, this)({}, data);
                    return;
                }
                Board.project_editor.on_summary_loaded($(data));
            }, // on_create_submit_done

            action_on_delete_popover: function(action) {
                Board.project_editor.$modal_footer.find('.btn-delete').popover(action);
            }, // hide_delete_popover

            on_cancel_deletion: function(ev) {
                Board.project_editor.action_on_delete_popover('hide');
            }, // on_cancel_deletion

            on_confirm_deletion: function(ev) {
                var $form = Board.project_editor.$modal_body.find('form'), context;
                if ($form.data('disabled')) { return false; }

                context = Board.project_editor.handle_form($form, ev);
                if (context == false) { return false;}

                Board.project_editor.action_on_delete_popover('hide');
                Board.project_editor.$modal_footer.find('.btn-delete').addClass('loading');
                Board.project_editor.$modal.find('.alert').remove();

                context.action_name = 'delete';

                Board.project_editor.$modal[0].setAttribute('data-front-uuid', context.uuid);

                FormTools.post_form_with_uuid($form, context,
                    Board.project_editor.on_delete_submit_done,
                    Board.project_editor.on_submit_failed,
                    [{name: 'csrfmiddlewaretoken', value: $form[0].csrfmiddlewaretoken.value}],
                    $form.data('delete-url')
                );

            }, // on_confirm_deletion

            on_delete_submit_done: function(data) {
                Board.project_editor.on_summary_loaded($(data));
                Board.deactivate();
            }, // on_delete_submit_done

            on_modal_hide: function(ev) {
                if (Board.project_editor.$modal.hasClass('edit-mode')) {
                    // disallow exit via esc if in edit mode (input has focus)
                    if (Board.project_editor.$modal_body.find('form :input:focus').length) {
                        ev.preventDefault();
                    }
                }
            }, // on_modal_hide

            on_modal_hidden: function(ev) {
                if (Board.project_editor.create_mode) {
                    $('#main').children('.empty-area').text('Please select a board');
                    Board.selector.$select.select2('open');
                }
            }, // on_modal_hidden

            subscribe_updates: function() {
                WS.subscribe(
                    'gim.front.Repository.' + main_repository_id + '.model.updated.is.Project',
                    'Board__project_editor__on_update_alert',
                    Board.project_editor.on_update_alert,
                    'prefix'
                );
                WS.subscribe(
                    'gim.front.Repository.' + main_repository_id + '.model.deleted.is.Project',
                    'Board__project_editor__on_delete_alert',
                    Board.project_editor.on_delete_alert,
                    'prefix'
                );
            }, // subscribe_updates

            can_update_on_alert: function(method, topic, args, kwargs) {
                if (typeof Board.project_editor.updating_ids[kwargs.id] != 'undefined' || kwargs.front_uuid && UUID.exists(kwargs.front_uuid) && UUID.has_state(kwargs.front_uuid, 'waiting')) {
                    setTimeout(function() {
                        Board.project_editor[method](topic, args, kwargs);
                    }, 100);
                    return false;
                }
                Board.project_editor.updating_ids[kwargs.id] = true;
                return true;
            }, // can_update_column_on_alert

            on_update_alert: function(topic, args, kwargs) {
                if (!kwargs.model || kwargs.model != 'Project' || !kwargs.id || !kwargs.number) {
                    return;
                }

                if (!Board.project_editor.can_update_on_alert('on_update_alert', topic, args, kwargs)) {
                    return;
                }

                var is_current = false;
                if (Board.mode == 'project' && kwargs.number == Board.$container.data('key')) {
                    is_current = true
                } else if (Board.project_editor.create_mode && kwargs.front_uuid && kwargs.front_uuid == Board.project_editor.$modal.attr('data-front-uuid')) {
                    is_current = true;
                }

                if (is_current) {
                    if (Board.project_editor.create_mode) {
                        Board.project_editor.show_modal_for_created(kwargs.url);
                    } else {
                        Board.project_editor.load_summary();
                    }
                }

                Board.selector.on_update_project_alert(topic, args, kwargs);

                // update the title
                if (is_current) {
                    var $title = $document.find('head > title');
                    var parts = $title.text().split(' | ');
                    for (var i = 0; i < parts.length; i++) {
                        if (parts[i].indexOf('Board - ') == 0) {
                            parts[i] = 'Board - ' + kwargs.name;
                            break;
                        }
                    }
                    $title.text(parts.join(' | '));
                }

                if (!kwargs.front_uuid || !UUID.exists(kwargs.front_uuid)) {
                    var verb = kwargs.is_new ? 'created' : 'updated', message;
                    if (is_current) {
                        message = 'The current project was just ' + verb;
                    } else {
                        message = 'The project named "' + kwargs.name + '" was just ' + verb;
                    }
                    MessagesManager.add_messages([MessagesManager.make_message(message, 'info')]);
                }

                if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                    UUID.set_state(kwargs.front_uuid, '');
                }
                delete Board.project_editor.updating_ids[kwargs.id];

            }, // on_update_alert

            show_modal_for_created: function(url) {
                var modal_ready = Board.project_editor.$modal_footer.find('.alert').length,
                    div_alert = '<div class="alert alert-info">' + "This project was just created. You'll be redirected to its page" + '</div>';

                if (!modal_ready) {
                    Board.project_editor.$modal_body.empty().append(div_alert);
                }
                Board.project_editor.$modal_footer.empty().append(
                    '<div class="row-fluid align-left"><div class="span12"><button class="btn btn-blue" data-dismiss="modal">Ok</button></div></div>'
                );
                if (modal_ready) {
                    Board.project_editor.$modal_footer.prepend(div_alert);
                }
                Board.project_editor.$modal.off('hide.modal', Board.project_editor.on_modal_hide);
                Board.project_editor.$modal.off('hidden.modal', Board.project_editor.on_modal_hide);
                Board.project_editor.$modal.on('hidden.modal', function() {
                    window.location.href = url;
                });
                Board.project_editor.$modal.modal('show');
            }, // show_modal_for_deleted

            show_modal_for_deleted: function() {
                Board.project_editor.$modal_body.empty().append(
                    '<div class="alert alert-error">' +
                    "This project was just deleted. You'll be redirected to the Board home page" +
                    '</div>'
                );
                Board.project_editor.$modal_footer.empty().append(
                    '<div class="row-fluid align-left"><div class="span12"><button class="btn btn-blue" data-dismiss="modal">Ok</button></div></div>'
                );
                Board.project_editor.$modal.off('hide.modal', Board.project_editor.on_modal_hide);
                Board.project_editor.$modal.off('hidden.modal', Board.project_editor.on_modal_hide);
                Board.project_editor.$modal.on('hidden.modal', function() {
                    window.location.href = '/' + $body.data('repository') + '/board/';
                });
                Board.project_editor.$modal.modal('show');
            }, // show_modal_for_deleted

            on_delete_alert: function(topic, args, kwargs) {
                if (!kwargs.model || kwargs.model != 'Project' || !kwargs.id || !kwargs.number) {
                    return;
                }

                if (!Board.project_editor.can_update_on_alert('on_delete_alert', topic, args, kwargs)) {
                    return;
                }

                var is_current = (kwargs.number == Board.$container.data('key'));

                if (is_current) {
                    Board.deactivate();
                    Board.project_editor.show_modal_for_deleted();
                }

                Board.selector.on_delete_project_alert(topic, args, kwargs);

                if (!is_current) {
                    MessagesManager.add_messages([MessagesManager.make_message(
                        'The project named "' + kwargs.name + '" was just deleted', 'info')]);
                }

                if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                    UUID.set_state(kwargs.front_uuid, '');
                }
                delete Board.project_editor.updating_ids[kwargs.id];
            }, // on_delete_alert

            init: function() {
                Board.project_editor.subscribe_updates();

                if (!Board.project_editor.$modal.length) {
                    return;
                }

                Board.project_editor.$modal_header = Board.project_editor.$modal.children('.modal-header');
                Board.project_editor.$modal_body = Board.project_editor.$modal.children('.modal-body');
                Board.project_editor.$modal_footer = Board.project_editor.$modal.children('.modal-footer');
                Board.project_editor.create_mode = !!Board.project_editor.$modal.data('create-mode');

                if (Board.project_editor.create_mode) {
                    Board.project_editor.$modal.one('shown.modal', function() {
                        console.log('shown');
                        var $input =  Board.project_editor.$modal_body.find('input[name=name]');
                        $input.focus();
                        FormTools.move_cursor_at_the_end($input);
                    });
                    Board.project_editor.$modal.modal('show');
                    $document.on('click', '#project-editor button.btn-cancel', Board.project_editor.exit_edit_mode);
                    $document.on('click', '#project-editor button.btn-edit-submit', Board.project_editor.on_edit_submit_click);
                    $document.on('submit', '#project-editor .project-create-form', Board.project_editor.on_create_submit);
                } else if (Board.mode == 'project') {
                    if (Board.project_editor.$modal.data('waiting-for-deletion') || Board.project_editor.$modal.data('waiting-for-creation')) {
                        Board.deactivate();
                        Board.project_editor.$modal.modal('show');
                    }
                    $document.on('click', '#project-editor button.btn-edit', Board.project_editor.on_edit_click);
                    $document.on('click', '#project-editor .cancel-deletion', Board.project_editor.on_cancel_deletion);
                    $document.on('click', '#project-editor .confirm-deletion', Board.project_editor.on_confirm_deletion);
                    $document.on('click', '#project-editor button.btn-cancel', Board.project_editor.exit_edit_mode);
                    $document.on('click', '#project-editor button.btn-edit-submit', Board.project_editor.on_edit_submit_click);
                    $document.on('submit', '#project-editor .project-edit-form', Board.project_editor.on_edit_submit);
                }

                Board.project_editor.$modal.on('hide.modal', Board.project_editor.on_modal_hide);
                Board.project_editor.$modal.on('hidden.modal', Board.project_editor.on_modal_hidden);
            } // init

        }, // project_editor

        notes: {

            on_edit_or_delete_click: function () {
                var $link = $(this),
                    $note_node = $link.closest('li.note-item');
                if ($link.parent().hasClass('disabled')) { return false; }
                $note_node.find('a.btn-loading').addClass('loading');
                $note_node[0].IssuesListIssue.set_current(true);
                $.get($link.attr('href'))
                    .done($.proxy(Board.notes.on_edit_or_delete_loaded, {$note_node: $note_node, $link: $link}))
                    .fail($.proxy(Board.notes.on_edit_or_delete_load_failed, {$note_node: $note_node, $link: $link, text: 'edit'}));
                return false;
            }, // on_edit_or_delete_click

            on_edit_or_delete_loaded: function (data) {
                if (!data.trim() || data == 'error') {  // error if 409 from on_edit_or_delete_load_failed
                    this.$note_node.find('a.btn-loading.loading').removeClass('loading');
                    return false;
                }
                var $data = $(data).children();
                this.$note_node.addClass('edit-mode').empty().append($data);
                var $textarea = $data.find('textarea');
                if ($textarea.length && !$(':input:focus').length) {
                    $textarea.focus();
                }
            }, // on_edit_or_delete_load_failed

            on_edit_or_delete_load_failed: function (xhr, data) {
                if (xhr.status == 409) {
                    // 409 Conflict Indicates that the request could not be processed because of
                    // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                    return $.proxy(Board.notes.on_edit_or_delete_loaded, this)(data);
                }
                this.$note_node.find('a.btn-loading.loading').removeClass('loading');
                alert('Unable to load the ' + this.text + ' form!')
            }, // on_edit_or_delete_load_failed

            on_edit_or_delete_cancel_click: function () {
                var $node = $(this).closest('li.note-item');

                FormTools.disable_form($node.find('form'));

                $.get($node.data('url'))
                    .done(function(data) {
                        var $data = $(data).children();
                        $node.empty().removeClass('edit-mode').append($data);
                    })
                    .fail(function() {
                        alert('Unable to retrieve the original note')
                    });
            }, // on_edit_or_delete_cancel_click

            on_submit: function (ev, is_create) {
                var $form = $(this), front_uuid, context;
                if ($form.data('disabled')) { return false; }

                front_uuid = is_create ? $form.closest('.note-item')[0].id.substr(5) : null;
                context = FormTools.handle_form($form, ev, front_uuid);
                if (context === false) { return false; }

                var $textarea = $form.find('textarea');

                if ($textarea.length && !$textarea.val().trim()) {
                    $textarea.after('<div class="alert alert-error">You must enter a note</div>');
                    $form.find('button').removeClass('loading');
                    FormTools.enable_form($form);
                    $textarea.focus();
                    return false;
                }

                $form.closest('li.note-item')[0].setAttribute('data-front-uuid', context.uuid);

                FormTools.post_form_with_uuid($form, context,
                    is_create ? Board.notes.on_add_submit_done : Board.notes.on_submit_done,
                    Board.notes.on_submit_failed
                );
            }, // on_submit

            on_submit_done: function (data) {
                var $node = $('li.note-item[data-front-uuid=' + this.uuid + ']');
                if ($node.length) {
                    var $data = $(data).children();
                    $node.empty().removeClass('edit-mode').append($data);
                }
            }, // on_submit_done

            on_submit_failed: function (xhr, data) {
                if (xhr.status == 409) {
                    // 409 Conflict Indicates that the request could not be processed because of
                    // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                    this.$form.find('button.submit').remove();
                    FormTools.enable_form(this.$form);
                    var $textarea = this.$form.find('textarea');
                    $textarea.after('<div class="alert alert-error">The note cannot be saved for now. Copy the text if you need, then cancel and retry in a few seconds.</div>');
                    return
                }
                FormTools.enable_form(this.$form);
                this.$form.find('.alert').remove();
                var $textarea = this.$form.find('textarea');
                $textarea.after('<div class="alert alert-error">We were unable to post this note</div>');
                this.$form.find('button').removeClass('loading');
                $textarea.focus();
            }, // on_submit_failed

            on_add_click: function() {
                var $link = $(this),
                    $list = $link.closest('.issues-list'),
                    $group = $link.closest('.issues-group'),
                    url = $list.data('create-note-url'),
                    group, $group_header;

                if (!$group.length) {
                    group = $list[0].IssuesList.create_group(null, null, null);
                    group.ask_for_filtered_issues_update();
                    $group = group.$node;
                    $link = $group.find('.note-add-btn')
                }

                $group_header = $link.closest('.box-header');

                $.get(url)
                    .done(function(data) {
                        var $new_notes_holder = $group.children('ul.new-notes-holder');
                        if (!$new_notes_holder.length) {
                            $new_notes_holder = $('<ul class="unstyled box-content new-notes-holder"></ul>');
                        }
                        $group_header.after($new_notes_holder);
                        var $data = $(data);
                        $data.addClass('edit-mode');
                        $new_notes_holder.append($data);
                        if (!$(':input:focus').length) {
                            $data.find('textarea').focus();
                        }
                    })
                    .fail(function() {
                        alert('Unable to retrieve the form to create a new note')
                    });

                return false;

            }, // on_add_click

            remove_add_item_node: function ($node) {
                var $new_notes_holder = $node.parent(),
                    group = $new_notes_holder.closest('.issues-group')[0].IssuesListGroup;
                $node.remove();
                if (!$new_notes_holder.children().length) {
                    $new_notes_holder.remove();
                    if (!group.issues.length) {
                        group.list.remove_group(group);
                    }
                }
            },

            on_add_cancel_click: function() {
                Board.notes.remove_add_item_node($(this).closest('li.note-item'));
            }, // on_add_cancel_click

            on_add_submit: function(ev) {
                return Board.notes.on_submit.bind(this)(ev, true);
            }, // on_add_submit

            on_add_submit_done: function (data) {
                var $node = this.$form.closest('li.note-item'),
                    list = $node.closest('.issues-list')[0].IssuesList,
                    $data = $(data),
                    issue = new IssuesList.IssuesListIssue($data[0], null),
                    group = list.groups[0];

                $data[0].setAttribute('data-front-uuid', this.uuid);

                Board.notes.remove_add_item_node(this.$form.closest('li.note-item'));

                group.add_issue(issue, true);
                group.open();
                list.ask_for_quicksearch_results_reinit();
            }, // on_add_submit_done

            init: function() {
                if (!Board.$columns.length) { return; }

                $document.on('click', '.note-edit-btn, .note-delete-btn', Ev.stop_event_decorate(Board.notes.on_edit_or_delete_click));
                $document.on('submit', '.note-form:not(.note-create-form)', Board.notes.on_submit);
                $document.on('click', '.note-edit-form button[type=button], .note-delete-form button[type=button]', Board.notes.on_edit_or_delete_cancel_click);
                $document.on('click', '.note-add-btn', Ev.stop_event_decorate(Board.notes.on_add_click));
                $document.on('click', '.note-create-form button[type=button]', Board.notes.on_add_cancel_click);
                $document.on('submit', '.note-create-form', Board.notes.on_add_submit);
                $document.on('focus', '.new-notes-holder .note-item :input', function() { $(this).closest('.note-item').addClass('active');} );
                $document.on('blur', '.new-notes-holder .note-item :input', function() { $(this).closest('.note-item').removeClass('active');} );
            }
        }, // Board.notes

        on_scroll: function(ev) {
            Board.lists.load_visible(500);
        }, //scroll

        update_dimensions: function() {
            Board.dimensions.scrollWidth = Board.$container[0].scrollWidth;
            Board.dimensions.scrollLeftMax = Board.$container[0].scrollLeftMax || (Board.dimensions.scrollWidth -  Board.$container[0].offsetWidth);
        }, // update_dimensions

        deactivate: function() {
            IssuesFilters.add_waiting(Board.filters.$options_node);
            IssuesFilters.add_waiting($(Board.filters.filters_selector));
            IssuesFilters.add_waiting(Board.$container);
        }, // deactivate

        init: function() {
            HoverIssue.delay_enter = 1000;

            if (Board.$container.length) {
                Board.container = Board.$container[0];
                Board.mode = Board.$container.data('mode');
                Board.editable = Board.$container.data('editable');
            }

            Board.filters.init();
            Board.lists.init();
            Board.selector.init();
            Board.arranger.init();
            Board.notes.init();
            Board.project_editor.init();

            if (Board.container) {
                Board.update_dimensions();
                Board.base_url = Board.$container.data('base_url');
                Board.container.addEventListener('scroll', Board.on_scroll); // no jquery overhead
                if (Board.editable) {
                    Board.dragger.init();
                } else {
                    MessagesManager.add_messages([MessagesManager.make_message("You are only allowed to see this board.", 'info')]);
                }
            }
        } // init

    }; // Board

    IssuesList.prototype.close = function close () {
        Board.arranger.hide_column(this.$container_node.closest('.board-column'));
        return false;
    };

    IssuesList.prototype.set_current_original = IssuesList.prototype.set_current;
    IssuesList.prototype.set_current = (function IssuesList__set_current () {
        this.set_current_original();
        if (!Board.$columns.length) { return; }
        var $column = this.$node.closest('.board-column');
        $('.board-column.is-active').removeClass('is-active');
        $column.addClass('is-active');
        if (!Board.dimensions.scrollLeftMax) { return; }
        var column_left = $column.position().left,
            column_width = $column.width(),
            column_right = column_left + column_width,
            container_left = Board.container.scrollLeft,
            container_width = Board.container.offsetWidth,
            scroll_to = null;

        if (column_right > container_width) {
            scroll_to = container_left + column_right - container_width;
        } else if (column_left < 0) {
            scroll_to = container_left + column_left;
        }
        Board.lists.scroll_to(scroll_to);

    }); // IssuesList__set_current

    IssuesList.prototype.create_group_original = IssuesList.prototype.create_group;
    IssuesList.prototype.create_group = (function IssuesList__create_group (filter_value, filter_text, filter_description) {
        this.$node.children('.issues-group.empty-sortable').remove();
        return this.create_group_original(filter_value, filter_text, filter_description);
    }); // IssuesList__create_group

    IssuesList.prototype.remove_group_original = IssuesList.prototype.remove_group;
    IssuesList.prototype.remove_group = (function IssuesList__remove_group (group) {
        var $new_notes_holder = group.$node.children('ul.new-notes-holder');
        if ($new_notes_holder.length) { return; }
        this.remove_group_original(group);
        $.proxy(Board.dragger.on_column_loaded, this.$container_node)();
    }); // IssuesList__remove_group

    IssuesList.on_before_update_card_alert = (function IssuesList_on_before_update_card_alert (topic, args, kwargs) {
        if (kwargs.model && kwargs.model == 'Card' && kwargs.id && !kwargs.issue) {
            // we're updating a note

            kwargs.js_id = 'note-' + kwargs.id;

            if (!IssuesList.can_update_on_alert(kwargs, 'on_update_card_alert', topic, args, kwargs)) {
                return;
            }

            var loaded_lists = IssuesList.get_loaded_lists(),
                managed = false;

            for (var i = 0; i < loaded_lists.length; i++) {
                var list = loaded_lists[i],
                    can_display_notes = list.$node.data('can-display-notes'),
                    project_number, column_id, issue, can_handle_note,
                    selector, $nodes;

                if (!can_display_notes) {
                    continue;
                }

                project_number = list.filtered_project_number;
                column_id = list.$container_node.data('key');
                can_handle_note = project_number && column_id && project_number == kwargs.project_number && parseInt(column_id, 10) == kwargs.column_id;


                selector = 'li.note-item#' + kwargs.js_id;
                if (kwargs.front_uuid) {
                    selector += ', li.note-item[data-front-uuid=' + kwargs.front_uuid + ']';
                }
                $nodes = list.$node.find(selector);
                if ($nodes.length) {
                    issue = $nodes[0].IssuesListIssue;

                    // not a column the note should be, we have the issue, we remove it
                    if (!can_handle_note) {
                        issue.group.remove_issue(issue);
                        continue;
                    }

                    // the note should definitely be in this column, we have the issue, we update it
                    managed = true;
                    (function(issue) {
                        $.get(kwargs.url)
                            .done(function(data) {
                                var $data = $(data);
                                issue.$node.replaceWith($data);
                                issue.prepare($data[0]);
                                issue.set_issue_ident({
                                    number: issue.$node.data('issue-number'),
                                    id: issue.$node.data('issue-id'),
                                    repository: issue.$node.data('repository'),
                                    repository_id: issue.$node.data('repository-id')
                                });
                                issue.group.ask_for_reorder();
                            })
                            .always(function() {
                                if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                                    UUID.set_state(kwargs.front_uuid, '');
                                }
                                delete IssuesList.updating_ids[kwargs.js_id];
                            });
                    })(issue);

                } else {
                    // not a column the note should be, we don't have the issue, nothing to do
                    if (!can_handle_note) {
                        continue;
                    }

                    // the note should definitely be in this column, we don't have the issue, we fetch it to add it
                    managed = true;
                    (function(list) {
                        $.get(kwargs.url)
                            .done(function(data) {
                                var $data = $(data),
                                    front_uuid_exists = UUID.exists(kwargs.front_uuid),
                                    issue = new IssuesList.IssuesListIssue($data[0], null),
                                    group = list.groups.length ? list.groups[0] : list.create_group(null, null, null);

                                $data.addClass('recent');
                                group.add_issue(issue, true);
                                if (list.groups.length == 1) {
                                    group.open();
                                } else {
                                    group.$node.addClass('recent');
                                }
                                list.ask_for_quicksearch_results_reinit();

                                if (kwargs.front_uuid && kwargs.is_new && front_uuid_exists) {
                                    $data.removeClass('recent');
                                }

                            })
                            .always(function() {
                                if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                                    UUID.set_state(kwargs.front_uuid, '');
                                }
                                delete IssuesList.updating_ids[kwargs.js_id];
                            });
                    })(list);

                }
            }

            if (!managed) {
                if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                    UUID.set_state(kwargs.front_uuid, '');
                }
                delete IssuesList.updating_ids[kwargs.js_id];
            }

            return true;

        }

        return false;

    }); // IssuesList_on_before_update_card_alert

    IssuesList.on_before_delete_card_alert = (function IssuesList_on_before_delete_card_alert (topic, args, kwargs) {
        if (kwargs.model && kwargs.model == 'Card' && kwargs.id && !kwargs.issue) {
            // we're updating a note

            kwargs.js_id = 'note-' + kwargs.id;

            if (!IssuesList.can_update_on_alert(kwargs, 'on_delete_card_alert', topic, args, kwargs)) {
                return;
            }

            var loaded_lists = IssuesList.get_loaded_lists();

            for (var i = 0; i < loaded_lists.length; i++) {
                var list = loaded_lists[i],
                    issue = list.get_issue_by_id(kwargs.js_id);
                if (issue) {
                    // we have the note in this list, we remove it
                    issue.group.remove_issue(issue);
                }
            }

            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                UUID.set_state(kwargs.front_uuid, '');
            }
            delete IssuesList.updating_ids[kwargs.js_id];


            return true;

        }

        return false;
    }); // IssuesList_on_before_delete_card_alert

    Math.easeInOutQuad = function (t, b, c, d) {
      t /= d/2;
      if (t < 1) {
        return c/2*t*t + b
      }
      t--;
      return -c/2 * (t*(t-2) - 1) + b;
    };

    window.Board = Board;
    Board.init();
});
