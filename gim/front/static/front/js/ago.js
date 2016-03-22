var time_ago = (function () {
    "use strict";
    var origin = new Date(document.body.getAttribute('data-base-datetime')),
        start = new Date(),
        content_method = ('textContent' in document.body) ? 'textContent' : 'innerHTML',
        halfstr = "½",
        nohalf = '',
        dict = {
            'short': {
                'now': 'now',
                'mn': '1 mn',
                'mns': ' mn',
                'h': '1 h',
                'hs': ' h',
                'd': '1 d',
                'ds': ' d',
                'w': '1 w',
                'ws': ' w',
                'mo': '1 mo',
                'mos': ' mo',
                'y': '1 y',
                'ys': ' y'
            },
            'long': {
                'now': 'just now',
                'mn': 'a minute ago',
                'mns': ' minutes ago',
                'h': 'an hour ago',
                'hs': ' hours ago',
                'd': 'a day ago',
                'ds': ' days ago',
                'w': 'a week ago',
                'ws': ' weeks ago',
                'mo': 'a month ago',
                'mos': ' months ago',
                'y': 'a year ago',
                'ys': ' years ago'
            }
        };

    function update_start(server_date) {
        // When the page is reloaded from cache, the content of the body attribute may be not
        // accurate anymore, so we provide a way to reset it, passing a date in the same format
        // as expected in the body attribute;
        start = new Date();
        origin = new Date(server_date);
    }

    function divmod(x, y) {
        return [(x - x % y) / y, x % y];
    }

    function ago(delta, is_short) {
        // based on https://github.com/twidi/pytimeago, to share same return result
        var fmt, mins, hours, half, days, wdays, weeks, months, years, years_and_months,
            hours_and_mins, days_and_hours, weeks_and_wdays, months_and_days;

        fmt = dict[is_short ? 'short' : 'long'];

        // now
        if (delta < 0.5) {
            return fmt.now;
        }

        // < 1 hour
        mins = Math.round(delta / 60);
        if (mins < 1.5) {
            return fmt.mn;
        }
        if (mins < 60) {
            return Math.ceil(mins) + fmt.mns;
        }

        // < 1 day
        if (mins < 75) {
            return fmt.h;
        }
        hours_and_mins =  divmod(mins, 60);
        hours = Math.round(hours_and_mins[0]);
        mins = hours_and_mins[1];
        if (15 <= mins && mins <= 45) {
            half = halfstr;
        } else {
            half = nohalf;
            if (mins > 45) {
                hours++;
            }
        }
        if (hours < 24) {
            return hours + half + fmt.hs;
        }

        //  < 7 days
        if (hours < 30) {
            return fmt.d;
        }
        days_and_hours = divmod(hours, 24);
        days = Math.round(days_and_hours[0]);
        hours = days_and_hours[1];
        if (6 <= hours && hours <= 18) {
            half = halfstr;
        } else {
            half = nohalf;
            if (hours > 18) {
                days++;
            }
        }
        if (days < 7) {
            return days + half + fmt.ds;
        }

        // < 4 weeks
        if (days < 9) {
            return fmt.w;
        }
        weeks_and_wdays = divmod(days, 7);
        weeks = Math.round(weeks_and_wdays[0]);
        wdays = weeks_and_wdays[1];
        if (2 <= wdays && wdays <= 4) {
            half = halfstr;
        } else {
            half = nohalf;
            if (wdays > 4) {
                weeks++;
            }
        }
        if (weeks < 4) { // So we don't get 4 weeks
            return weeks + half + fmt.ws;
        }

        // < year
        if (days < 40) {
            return fmt.mo;
        }
        months_and_days = divmod(days, 30.4);
        months = Math.round(months_and_days[0]);
        days = months_and_days[1];
        if (10 <= days && days <= 20) {
            half = halfstr;
        } else {
            half = nohalf;
            if (days > 20) {
                months++;
            }
        }
        if (months < 12) {
            return months + half + fmt.mos;
        }

        // Don't go further
        if (months < 16) {
            return fmt.y;
        }
        years_and_months = divmod(months, 12);
        years = Math.round(years_and_months[0]);
        months = years_and_months[1];
        if (4 <= months && months <= 8) {
            half = halfstr;
        } else {
            half = nohalf;
            if (months > 8) {
                years++;
            }
        }
        return years + half + fmt.ys;

    } // ago

    function replace(node) {
        var date_str, date, delta, is_short;

        date_str = node.getAttribute('data-datetime');
        if (!date_str) { return; }

        date = new Date(date_str);
        delta = (origin - date + (new Date() - start)) / 1000;
        if (isNaN(delta)) { return; }

        is_short = (node.className.indexOf('ago-short') >= 0);
        node[content_method] = ago(delta, is_short);
    }

    function update_ago(node) {
        var nodes = Array.prototype.slice.call((node || document).getElementsByClassName('ago')), i;
        for (i = 0; i < nodes.length; i++) {
            replace(nodes[i]);
        }
    }

    return {
        replace: update_ago,
        update_start: update_start
    };

})();
