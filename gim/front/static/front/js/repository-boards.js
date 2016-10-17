$().ready(function() {

    var $document = $(document),
        $body = $('body');
        body_id = $body.attr('id'),
        main_repository_id = $body.data('repository-id');

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
            $trigger: $('#board-columns-arranger-trigger'),
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
                        Board.arranger.$trigger.dropdown('toggle');
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
                Board.arranger.$trigger.one('focus', Board.arranger.init_select2);
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
                var $this = $(this);
                Board.arranger.remove_column($this.parent().prev(Board.lists.lists_selector).data('key'));
                $this.parents('.board-column').removeClass('mini small-title');
                return false;
            }, // on_closer_click

            on_minifier_click: function () {
                var $column = $(this).parents('.board-column'),
                    title = $column.find('.issues-list-title').first().text().trim(),
                    classes = 'mini';

                if (title.length <= 2) { classes += ' small-title'; }

                $column.addClass(classes);
                return false;
            },

            on_unminifier_click: function () {
                $(this).parents('.board-column').removeClass('mini small-title');
                return false;
            },

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
                requestNextAnimationFrame(function() { Board.dragger.update_sortables()});

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
                obj._mouseDrag = Board.dragger._sortable_override_mouse_drag;

                obj._oldRemoveCurrentsFromItems = obj._removeCurrentsFromItems
                obj._removeCurrentsFromItems = Board.dragger._sortable_override__removeCurrentsFromItems;

                obj._oldRearrange = obj._rearrange;
                obj._rearrange = Board.dragger._sortable_override_rearrage;
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
                    this.items = this.items.filter(item => item.item[0].IssuesListIssue.group.list != issue.group.list || item.item[0] == currentItem || (sibling && item.item[0].IssuesListIssue == sibling));
                }
            }, // _sortable_override__removeCurrentsFromItems

            _sortable_override_rearrage: function(event, i, a, hardRefresh) {
                if (!this.canMoveInsideSelf && this.currentItemSibling && i && i.item && i.item.length && i.item[0] == this.currentItemSibling) {
                    // We force the item to be back at its original position
                    this.direction = this.currentItemSiblingDirection == 1 ? 'down' : 'up';
                }
                this._oldRearrange(event, i, a, hardRefresh);
            }, // _sortable_override_rearrage

            _sortable_override_mouse_drag: function (event) {
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
                        list_changed = new_list != old_list,
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

                        pp = issue.project_positions
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
                                pp = old_group.issues[i].project_positions
                                if (pp[project_number] && pp[project_number].card_position && pp[project_number].card_position >= old_position) {
                                    pp[project_number].card_position -= 1;
                                }
                            }
                        }

                        // increment positions for ones with higher position in new group
                        if (new_list_can_handle_positions && new_position != -1) {
                            for (i = 0; i < new_group.issues.length; i++) {
                                if (new_group.issues[i] === issue) { continue; }
                                pp = new_group.issues[i].project_positions
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

                    }

                    // do we have to put the issue in another group on the same list
                    if (!new_list_can_handle_positions && group_changed && new_list.group_by_key) {
                        filter = issue.get_filter_for(new_list.group_by_key);
                        new_group = new_list.get_group_for_value(filter.value) || new_list.create_group(filter.value, filter.text, filter.description);
                        if (new_group != issue.group) {
                            new_list.change_issue_group(issue, new_group);
                        }
                    }

                    // we can now reorder
                    if (group_changed) {
                        old_group.ask_for_reorder();
                    }
                    new_group.ask_for_reorder();

                    if (group_changed || handle_positions && new_position != old_position) {
                        Board.dragger.remote_move_issue(issue, old_list, new_list, new_position && new_position > 0 ? new_position : null);
                    }

                    if (group_changed && !old_group.issues.length) {
                        old_list.remove_group(old_group);
                        $.proxy(Board.dragger.on_column_loaded, old_list.$container_node)();
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
                        position: position,
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

            update_dimensions: function() {
                Board.dragger.dimensions.scrollWidth = Board.$container[0].scrollWidth;
                Board.dragger.dimensions.scrollLeftMax = Board.$container[0].scrollLeftMax || (Board.dragger.dimensions.scrollWidth -  Board.$container[0].offsetWidth);
            }, // update_dimensions

            init: function() {
                if (!Board.$columns.length) { return; }
                Board.dragger.update_dimensions();
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
                var list, $filters_node, $issues_list_node;
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
                $document.on('focus', '.issues-list-search-main-board-trigger', Ev.set_focus(function () { return Board.filters.$seach_input; }, 200))

                Board.filters.add_history(window.location.href, true);
                window.HistoryManager.callbacks['BoardFilters'] = Board.filters.on_history_pop_state;
        } // init

        }, // Board.filters

        on_scroll: function(ev) {
            Board.lists.load_visible(500);
        }, //scroll

        init: function() {
            HoverIssue.delay_enter = 1000;

            if (Board.$container.length) {
                Board.container = Board.$container[0];
            }

            Board.filters.init();
            Board.lists.init();
            Board.selector.init();
            Board.arranger.init();

            if (Board.container) {
                Board.base_url = Board.$container.data('base_url');
                Board.container.addEventListener('scroll', Board.on_scroll); // no jquery overhead
                if (Board.$container.data('editable')) {
                    Board.dragger.init();
                } else {
                    MessagesManager.add_messages([MessagesManager.make_message("You are only allowed to see this board.", 'info')]);
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
        var $column = this.$node.closest('.board-column');
        $('.board-column.is-active').removeClass('is-active');
        $column.addClass('is-active');
        if (!Board.dragger.dimensions.scrollLeftMax) { return; }
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
