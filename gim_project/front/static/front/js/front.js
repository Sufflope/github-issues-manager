$().ready(function() {
    var $issue_container = $('#issue'),
        $issues_list_container = $('#issues-list'),
        current_issue_number = null;

    var on_issue_link_click = (function on_issue_link_click (e) {
        var link = this, $link = $(this), $item = $link.closest('.issue-item');
        e.preventDefault();
        e.stopPropagation();
        if ($item.hasClass('active')) { return; }
        current_issue_number = $link.data('issue-number');
        $.get(link.href, function(data) {
            if ($link.data('issue-number') != current_issue_number) { return; }
            $issue_container.html(data);
            $('.issue-item.active').removeClass('active');
            $item.addClass('active');
        });
    }); // on_issue_link_click

    var select_issues_group = (function select_issues_group($issues_group) {
        if (!$issues_group || !$issues_group.length) { return false; }
        $issues_group.find('.box-header').focus();
        current_issue_number = null;
        $('.issue-item.active').removeClass('active');
        $issue_container.html('<p class="empty-column">...</p>');
        return true;
    }); // select_issues_group

    var select_issue = (function select_issue($issue_link) {
        if (!$issue_link || !$issue_link.length) { return false; }

        // save the wanted issue number as the current one
        var issue_number = $issue_link.data('issue-number');
        current_issue_number = issue_number;

        var $list = $issue_link.closest('ul');
        var focus_and_link = function () {
            // remove the previously event set on this function
            $list.off('shown', focus_and_link);
            // is the wanted issue is still the current asked one, go
            if (issue_number == current_issue_number) {
                $issue_link.focus().click();
            }
        };

        if ($list.hasClass('collapse') && !$list.hasClass('in')) {
            // we are on a collapsed group, open it and when done, focus
            // the link
            $list.on('shown', focus_and_link);
            $list.collapse('show');
        } else {
            // normal and visible link, focus it
            focus_and_link();
        }

        return true;
    }); // select_issue

    var KEYUP = 38, KEYDOWN = 40, KEYLEFT=37, KEYRIGHT=39, KEYHOME = 36, KEYEND = 35;

    var on_issues_list_keydown = (function on_issues_list_keydown (e) {
        if (e.ctrlKey || e.shiftKey || e.metaKey) { return; }

        var $issue_item = $(this),
            something_done = false,
            $issue_link, $list, $group;

        switch (e.keyCode) {
             case KEYUP:
                // focus and click on the previous issue, or if no one, try to
                // go on the title of the current group
                $issue_link = $issue_item.prev().find('.issue-link').first();
                if (!$issue_link.length) {
                    select_issues_group($issue_item.closest('.issues-group'));
                }
                break;
             case KEYDOWN:
                // focus and click on the next issue, or if no one, try to go on
                // the title of the next group
                $issue_link = $issue_item.next().find('.issue-link').first();
                if (!$issue_link.length) {
                    select_issues_group($issue_item.closest('.issues-group').next());
                }
                break;
            case KEYHOME:
                // focus and click on the first issue on the group
                $issue_link = $issue_item.closest('.issues-group').find('.issue-link').first();
                break;
            case KEYEND:
                // focus and click on the last issue on the group
                $issue_link = $issue_item.closest('.issues-group').find('.issue-link').last();
                break;
            case KEYLEFT:
                // close the current group
                $list = $issue_item.closest('ul');
                if ($list.hasClass('collapse') && $list.hasClass('in')) {
                    $list.collapse('hide');
                    select_issues_group($issue_item.closest('.issues-group'));
                }
                break;
        } // switch

        if ($issue_link && $issue_link.length) {
            // doing stuff if a new issue link must be focused
            something_done = select_issue($issue_link);
        }

        if (something_done) {
            // stop event only if we did something with it
            e.preventDefault();
            e.stopPropagation();
        }
    }); // on_issues_list_keydown

    var on_issues_group_title_click = (function on_issues_group_title_click(e) {
        if (e.ctrlKey || e.shiftKey || e.metaKey) { return; }
        var $group_link = $(this),
            $group = $group_link.closest('.issues-group'),
            $list = $group.children('ul'),
            can_collapse = $list.hasClass('collapse'),
            open = (!can_collapse || $list.hasClass('in')),
            something_done = false,
            $previous_group, $previous_list;

        switch (e.keyCode) {
            case KEYUP:
                // focus and click on the last issue of the previous group if
                // it's open, or it's title if not
                $previous_group = $group.prev();
                $previous_list = $previous_group.children('ul');
                if ($previous_list.length) {
                    if (!$previous_list.hasClass('collapse') || $previous_list.hasClass('in')) {
                        something_done = select_issue($previous_list.find('.issue-link').last());
                    } else {
                        something_done = select_issues_group($previous_group);
                    }
                    something_done = true;
                }
                break;
            case KEYDOWN:
                // focus and click on the first issue of the group if open, or
                // focus on the title of the next group if not
                if (open) {
                    something_done = select_issue($group.find('.issue-link').first());
                } else {
                    something_done = select_issues_group($group.next());
                }
                break;
            case KEYLEFT:
                // close the group if open
                if (can_collapse && open) {
                    $list.collapse('hide');
                    something_done = true;
                }
                break;
            case KEYRIGHT:
                // open the group if closed
                if (can_collapse || !open) {
                    $list.collapse('show');
                    something_done = true;
                }
                break;
            case KEYHOME:
                // go to the title of the first group
                something_done = select_issues_group($issues_list_container.find('.issues-group').first());
                break;
            case KEYEND:
                // go to the title of the last group
                something_done = select_issues_group($issues_list_container.find('.issues-group').last());
                break;

        } // switch

        if (something_done) {
            // stop event only if we did something with it
            e.preventDefault();
            e.stopPropagation();
        }

    }); // on_issues_group_title_click

    var on_close_all_groups_click = (function on_close_all_groups_click(e) {
        $issues_list_container.find('.collapse').each(function() { $(this). collapse('hide'); });
    }); // on_close_all_groups_click

    var on_open_all_groups_click = (function on_open_all_groups_click(e) {
        $issues_list_container.find('.collapse').each(function() { $(this). collapse('show'); });
    }); // on_open_all_groups_click

    var on_toggle_details_click = (function on_toggle_details_click(e) {
        $issues_list_container.toggleClass('without-details');
    }); // on_toggle_details_click

    $(document).on('click', 'a.issue-link', on_issue_link_click);
    $(document).on('keydown', '.issue-item', on_issues_list_keydown);
    $(document).on('keydown', '.issues-group .box-header', on_issues_group_title_click);
    $(document).on('click', '#toggle-issues-details', on_toggle_details_click);
    $(document).on('click', '#close-all-groups', on_close_all_groups_click);
    $(document).on('click', '#open-all-groups', on_open_all_groups_click);

    select_issues_group($issues_list_container.find('.issues-group').first());
});
