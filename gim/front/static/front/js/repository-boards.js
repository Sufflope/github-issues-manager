$().ready(function() {

    var $document = $(document),
        $body = $('body');

    var Board = {
        container_selector: '#board-columns',
        $container: $('#board-columns'),
        container: null,
        $columns: $('.board-column'),
        base_url: null,

        selector: {
            $select: $('#board-selector'),

            format_option: function(state, $container) {
                var $option = $(state.element),
                    value = $option.attr('value');
                if (value == 'labels-editor') {
                    $container.addClass('labels-editor-link');
                    value = null;
                }
                if (!value) { return state.text; }
                var nb_columns = $option.data('columns');
                $container.attr('title', $option.attr('title'));
                $container.append($('<span/>').text($option.data('name')));
                $container.append($('<span style="float: right"/>').text(nb_columns + ' columns'));
            }, // format_option

            format_selection: function(state, $container) {
                var $option = $(state.element),
                    value = $option.attr('value');
                if (value == 'labels-editor') {
                    return '';
                }
                if (!value) { return state.text; }
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
                Board.dragger.on_columns_rearranged();
            }, // rearrange

            on_closer_click: function () {
                Board.arranger.remove_column($(this).prev(Board.lists.lists_selector).data('key'));
                return false;
            }, // on_closer_click

            animate_scroll_to: function() {
                if (!Board.lists.asked_scroll_to.running) { return; }
                Board.lists.asked_scroll_to.currentTime += Board.lists.asked_scroll_to.increment;
                var val = Math.easeInOutQuad(
                    Board.lists.asked_scroll_to.currentTime,
                    Board.lists.asked_scroll_to.start,
                    Board.lists.asked_scroll_to.change,
                    Board.lists.asked_scroll_to.duration
                );
                Board.container.scrollLeft = val;
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
                } else if (position > Board.dragger.dimensions.scrollLeftMax) {
                    position = Board.dragger.dimensions.scrollLeftMax;
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
                Board.lists.load_visible();
                $('.board-column-closer').on('click', Ev.stop_event_decorate(Board.lists.on_closer_click));
                jwerty.key('x', IssuesList.on_current_list_key_event('close'));

            } // init

        }, // Board.lists

        dragger: {
            activated: false,
            all_selector: '.board-column.loaded .issues-group:not(.template) .issues-group-issues',
            active_selector: '.issues-group-issues',  // '.board-column.loaded:not(.hidden) .issues-group:not(.template) .issues-group-issues',
            dimensions: {
                scrollLeftMax: 0,
                scrollWidth: 0
            },
            dragging: false,
            updating: false,
            $duplicate_hiddens: [],

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
                    Board.dragger.$duplicate_hiddens = $('.board-column #' + ui_item[0].id + ':not(.ui-sortable-placeholder):not(.ui-sortable-helper)').not(ui_item[0]);
                    if (Board.dragger.$duplicate_hiddens.length) {
                        Board.dragger.$duplicate_hiddens.hide();
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

                for (var i = 0; i < Board.dragger.$duplicate_hiddens.length; i++) {
                    var $item = $(Board.dragger.$duplicate_hiddens[i]);
                    // the item may have been removed so we check
                    if ($item.closest(document.documentElement).length) {
                        $item.show();
                    }
                }
                Board.dragger.$duplicate_hiddens = [];

                Board.$container.removeClass('dragging');
                var $list_node = ui.item.closest('.issues-list');
                ui.item.removeClass('force-without-details');

                Board.dragger.hide_empty_columns();
                requestNextAnimationFrame(Board.dragger.update_sortables);

            }, // on_drag_stop

            prepare_empty_list: function(list) {
                var group = list.create_group(null, null, null);
                group.$node.addClass('empty-sortable');
                group.list.create_empty_node();
                group.list.$empty_node.show();
                group.$count_node.text(0);
                group.$issues_node.addClass('in');
                group.collapsed = false;
                group.list.groups = [];  // we don't count it in groups to avoid navigating in it
            }, // prepare_empty_list

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
                    var list = IssuesList.get_for_node($list_container_node);
                    if (!list.$node.has('.issues-group:not(.template)').length) {
                        Board.dragger.prepare_empty_list(list);
                    }
                    Board.dragger.update_sortables(true);
                });
            }, // on_column_loaded

            on_columns_rearranged: function() {
                if (!Board.dragger.activated) { return; }
                requestNextAnimationFrame(function() {
                    Board.dragger.update_dimensions();
                    Board.dragger.update_sortables(true);
                });
            }, // on_columns_rearranged

            on_sortable_create: function(ev, ui) {
                var obj = $(this).data('ui-sortable');
                obj._mouseDrag = Board.dragger.sortable_mouse_drag;
            }, // on_sortable_create
            
            sortable_mouse_drag: function (event) {
                // copy of _mouseDrag from jqueryUI.sortable, to not scroll more than the max of the board
                // see `CHANGED HERE` parts
                var i, item, itemElement, intersection,
                    o = this.options,
                    scrolled = false;

                //Compute the helpers position
                this.position = this._generatePosition(event);
                // CHANGED HERE: we don't want the helper to overflow on the right
                this.position.left = Math.min(this.position.left, Board.dragger.dimensions.scrollWidth - this.helperProportions.width);

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

                        // CHANGED HERE: added max with Board.dragger.dimensions.scrollLeftMax
                        if((this.overflowOffset.left + this.scrollParent[0].offsetWidth) - event.pageX < o.scrollSensitivity) {
                            this.scrollParent[0].scrollLeft = scrolled = Math.min(this.scrollParent[0].scrollLeft + o.scrollSpeed, Board.dragger.dimensions.scrollLeftMax);
                        } else if(event.pageX - this.overflowOffset.left < o.scrollSensitivity) {
                            this.scrollParent[0].scrollLeft = scrolled = Math.min(this.scrollParent[0].scrollLeft - o.scrollSpeed, Board.dragger.dimensions.scrollLeftMax);
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

            }, // sortable_mouse_drag

            create_placeholder: function(currentItem) {
                return currentItem.clone().addClass('ui-sortable-placeholder').append('<div class="mask"/>').show();
            }, // create_placeholder

            on_drag_receive: function(ev, ui) {
                var receiver = this,
                    issue = ui.item[0].IssuesListIssue;

                requestNextAnimationFrame(function() {
                    var $new_group = $(receiver).parent(),
                        new_group = $new_group[0].IssuesListGroup,
                        new_list = new_group.list,
                        old_group = issue.group,
                        old_list = old_group.list,
                        changed = new_group != old_group,
                        is_current = old_group.current_issue == issue,
                        $duplicates;

                    if ($new_group.hasClass('empty-sortable')) {
                        $new_group.removeClass('empty-sortable visible');
                        new_list.groups.push(new_group);
                    }

                    if (changed && is_current) {
                        issue.unset_current();
                    }

                    if (changed) {
                        $duplicates = new_list.$node.find('#issue-' + issue.id + '.issue-item:not(.ui-sortable-placeholder):not(.ui-sortable-helper)').not(issue.$node);
                        // we remove the existing one(s)
                        for (var i = 0; i < $duplicates.length; i++) {
                            $duplicates[i].IssuesListIssue.clean();
                        }
                    }

                    issue.group = new_group;
                    new_group.update_issues_list();

                    if (changed) {
                        if (is_current) {
                            issue.set_current();
                        }

                        Board.dragger.remote_move_issue(issue, old_list, new_list);

                        old_group.update_issues_list();

                        if (!old_group.issues.length) {
                            old_list.remove_group(old_group);
                            $.proxy(Board.dragger.on_column_loaded, old_list.$container_node)();
                        }
                    }
                });
            }, // on_drag_receive

            remote_move_issue: function(issue, old_list, new_list) {
                var new_key = new_list.$container_node.data('key'),
                    url = old_list.base_url + 'move/' + issue.number + '/to/' + new_key + '/',
                    front_uuid = UUID.generate('waiting'),
                    data = {csrfmiddlewaretoken: $body.data('csrf'), front_uuid: front_uuid},
                    context = {
                        old_list: old_list,
                        new_list: new_list,
                        issue: issue
                    };
                $.post(url, data)
                    .fail($.proxy(Board.dragger.on_remote_move_issue_failure, context))
                    .always(function() {UUID.set_state(front_uuid, '');});
            }, // remote_move_issue

            on_remote_move_issue_failure: function(xhr, data) {
                var context = this,
                    $message = $('<span/>').text("We couldn't update the issue ");
                $message.append($('<span style="font-weight: bold"/>').text(this.issue.$node.find('.issue-link').text()));
                $message.append($('<br/>'), $('<span/>').text('The related lists will be auto-reloaded in 5 seconds'));
                MessagesManager.add_messages(MessagesManager.make_message($message, 'error'));
                setTimeout(function() {
                    context.old_list.refresh();
                    context.new_list.refresh();
                }, 5000);
            }, // on_remote_move_issue_failure

            check_issue_movable: function(sortable_node, ui_item) {
                requestNextAnimationFrame(function() {
                    var $list_node = ui_item.closest('.issues-list'),
                        list = $list_node[0].IssuesList,
                        issue = ui_item[0].IssuesListIssue,
                        url = Board.base_url + 'can_move/' + issue.number + '/',
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
                        if (sortable.board_column.hasClass('hidden')) {
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
                    if ($column.hasClass('hidden')) {
                        continue;
                    }
                    refresh_needed = true;
                    $list.sortable({
                        helper: 'clone',
                        appendTo: Board.$container,
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
                        receive: Board.dragger.on_drag_receive
                    }).disableSelection();

                    $list.data('ui-sortable').board_column = $column;
                }

                if (refresh_needed) {
                    for (var j = 0; j < to_refresh.length; j++) {
                        to_refresh[j].sortable('refresh');
                    }
                }

                Board.dragger.updating = false;
            }, // update_sortables

            update_dimensions: function() {
                Board.dragger.dimensions.scrollWidth = Board.$container[0].scrollWidth;
                Board.dragger.dimensions.scrollLeftMax = Board.$container[0].scrollLeftMax || (Board.dragger.dimensions.scrollWidth -  Board.$container[0].offsetWidth);
            }, // update_dimensions

            init: function() {
                if (!Board.$columns.length) { return; }
                Board.dragger.update_dimensions();
                Board.dragger.activated = true;
                setTimeout(function() {
                    MessagesManager.add_messages(MessagesManager.make_message("Vertical position in a column won't be saved.", 'warning'));
                }, 2000);
            }
        }, // Board.dragger

        on_scroll: function(ev) {
            Board.lists.load_visible(500);
        }, //scroll

        init: function() {
            HoverIssue.delay_enter = 1000;

            if (Board.$container.length) {
                Board.container = Board.$container[0];
            }

            Board.lists.init();
            Board.selector.init();
            Board.arranger.init();

            if (Board.container) {
                Board.base_url = Board.$container.data('base_url');
                Board.container.addEventListener('scroll', Board.on_scroll); // no jquery overhead
                if (Board.$container.data('editable')) {
                    Board.dragger.init();
                } else {
                    MessagesManager.add_messages(MessagesManager.make_message("You are only allowed to see this board.", 'info'));
                }
            }
        } // init

    }; // Board

    IssuesList.prototype.close = function close () {
        Board.arranger.remove_column(this.$container_node.data('key'));
        return false;
    };

    IssuesList.prototype.set_current_original = IssuesList.prototype.set_current;
    IssuesList.prototype.set_current = (function IssuesList__set_current () {
        this.set_current_original();
        if (!Board.$columns.length) { return; }
        if (!Board.dragger.dimensions.scrollLeftMax) { return; }
        var $column = this.$node.closest('.board-column'),
            column_left = $column.position().left,
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
