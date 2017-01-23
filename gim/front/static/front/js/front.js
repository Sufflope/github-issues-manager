$().ready(function() {

    var UUID = (function() {
        /**
         * Fast UUID generator, RFC4122 version 4 compliant.
         * @author Jeff Ward (jcward.com).
         * @license MIT license
         * @link http://stackoverflow.com/questions/105034/how-to-create-a-guid-uuid-in-javascript/21963136#21963136
         **/
        var self = {};
        var lut = []; for (var i=0; i<256; i++) { lut[i] = (i<16?'0':'')+(i).toString(16); }
        var states = {};
        self.generate = function(state) {
            var d0 = Math.random()*0xffffffff| 0, d1 = Math.random()*0xffffffff| 0,
                d2 = Math.random()*0xffffffff| 0, d3 = Math.random()*0xffffffff|0;
            var uuid = lut[d0&0xff]+lut[d0>>8&0xff]+lut[d0>>16&0xff]+lut[d0>>24&0xff]+'-'+
                lut[d1&0xff]+lut[d1>>8&0xff]+'-'+lut[d1>>16&0x0f|0x40]+lut[d1>>24&0xff]+'-'+
                lut[d2&0x3f|0x80]+lut[d2>>8&0xff]+'-'+lut[d2>>16&0xff]+lut[d2>>24&0xff]+
                lut[d3&0xff]+lut[d3>>8&0xff]+lut[d3>>16&0xff]+lut[d3>>24&0xff];
            self.set_state(uuid, state || '');
            return uuid
        };
        self.exists = function(uuid) {
            return typeof states[uuid] !== 'undefined';
        };
        self.set_state = function(uuid, state) {
            states[uuid] = state;
        };
        self.has_state = function(uuid, state) {
            return states[uuid] === state;
        };
        return self;
    })();
    window.UUID = UUID;

    function GetVendorAttribute(prefixedAttributes) {
       var tmp = document.createElement("div");
       for (var i = 0; i < prefixedAttributes.length; ++i) {
           if (typeof tmp.style[prefixedAttributes[i]] != 'undefined') {
              return prefixedAttributes[i];
           }
       }
       return null;
    }

    var $document = $(document),
        $body = $('body'),
        body_id = $body.attr('id'),
        main_repository = $body.data('repository'),
        main_repository_id = $body.data('repository-id'),
        transform_attribute = GetVendorAttribute(["transform", "msTransform", "MozTransform", "WebkitTransform", "OTransform"]);

    var UrlParser = { // http://stackoverflow.com/a/6944772
        node: null,
        parse: function(url) {
            if (!UrlParser.node) {
                UrlParser.node = document.createElement('a');
            }
            UrlParser.node.href = url;
            return UrlParser.node; // access property: host, hostname, hash, href, pathname, port, protocol, search
        },
        remove_hash: function(url) {
            var previous = UrlParser.node ? UrlParser.node.href : null,
                parsed = UrlParser.parse(url);
            if (parsed.hash) {
                url = url.slice(0, url.length - parsed.hash.length);
            }
            if (previous) {
                UrlParser.parse(previous);
            }
            return url;
        }
    };
    window.UrlParser = UrlParser;

    var GithubNotifications = {
        on_page: (body_id == 'github_notifications')
    };

    var Favicon = {
        obj: null,
        init: function () {
            if (!Favicon.obj && window.Favico) {
                Favicon.obj = new window.Favico({
                    animation: 'popFade',
                    position: 'down',
                    type: 'circle',
                    bgColor: dynamic_favicon_colors.background,
                    textColor: dynamic_favicon_colors.text,
                    fontStyle: '600',
                    fontFamily: 'sans-serif'
                });
            }
            return !!Favicon.obj;
        }, // init

        set_val: function(val) {
            if (Favicon.init()) {
                if (!val) {
                    Favicon.obj.reset();
                } else {
                    Favicon.obj.badge(val);
                }
            }
        } // set

    }; // Favicon
    window.Favicon = Favicon;

    var Ev = {
        stop_event_decorate: (function stop_event_decorate(callback) {
            /* Return a function to use as a callback for an event
               Call the callback and if it returns false (strictly), the
               event propagation is stopped
            */
            return function(e) {
                if (e.isPropagationStopped()) { return false; }
                if (callback.bind(this)(e) === false) {
                    return Ev.cancel(e);
                }
            };
        }), // stop_event_decorate

        cancel: (function cancel(e) {
            /* A simple callback to use to simply cancel an event
            */
            e.preventDefault();
            e.stopPropagation();
            return false;
        }), // cancel

        stop_event_decorate_dropdown: (function stop_event_decorate_dropdown(callback, klass) {
            /* Return a function to use as a callback for clicks on dropdown items
               It will close the dropdown before calling the callback, and will
               return false to tell to the main decorator to stop the event
            */
            if (typeof klass === 'undefined') { klass = '.dropdown'; }
            var decorator = function(e) {
                var dropdown = $(e.target).closest(klass);
                $('.dropdown-backdrop').remove();
                if (dropdown.hasClass('open')) {
                    dropdown.children('.dropdown-toggle').dropdown('toggle');
                }
                return callback.bind(this)(e);
            };
            return Ev.stop_event_decorate(decorator);
        }), // stop_event_decorate_dropdown

        key_decorate: (function key_decorate(callback) {
            /* Return a function to use as a callback for a jwerty event
               Will cancel the call of the callback if the focus is actually on an
               input element.
               If not, the callback is called, and if it returns true
               (strictly), the event propagation is stopped
            */
            var decorator = function(e) {
                if ($(e.target).is(':input')) { return; }
                return callback(e);
            };
            return Ev.stop_event_decorate(decorator);
        }), // key_decorate

        charcode: (function charcode(charcode, callback) {
            /* Return a function to use as a callback for a key* event
               The callback will only be called if the charcode is the given one.
               Can be used with key_decorate
            */
            var decorator = function(e) {
                if (e.charCode != charcode) { return; }
                return callback(e);
            };
            return Ev.stop_event_decorate(decorator);
        }), // charcode

        set_focus: (function set_focus($node, delay) {
            /* Event handler to set the focus on the given node.
            */
            return function() {
                if (typeof $node == 'function') { $node = $node(); }
                if (delay) {
                    setTimeout(Ev.set_focus($node), delay);
                } else {
                    $node.focus();
                }
            }
        }) // set_focus
    };
    window.Ev = Ev;


    // globally manage escape key to close modal
    $document.on('keyup.dismiss.modal', Ev.key_decorate(function(ev) {
        if (ev.which != 27) { return; }
        var $modal = $('.modal.in');
        if (!$modal.data('modal').options.keyboard) { return; }
        $modal.modal('hide');
    }));

    var WS = {

        session: null,
        alert_ko_done: false,

        reconcile_mode: {
            active: false,
            first_received_msg_id: null,
            queue: []
        },

        last_msg_id: window.WS_last_msg_id,
        user_topic_key: window.WS_user_topic_key,

        subscriptions: {},

        $alert: {
            container: $('#ws-alert'),
            message: null,
            close: null
        },
        alert_time: null,

        get_subscribe_callback: (function WS__get_subscribe_callback (subscription, original_callback) {
            return function(args, kwargs, details) {

                if (typeof kwargs.ws_extra != 'undefined') {
                    details.extra = kwargs.ws_extra;
                    delete kwargs.ws_extra;
                }

                if (typeof details.extra != 'undefined') {
                    if (!details.extra.reconcile_mode && typeof details.extra.msg_id != 'undefined') {
                        if (WS.reconcile_mode.active && !WS.reconcile_mode.first_received_msg_id) {
                            WS.reconcile_mode.first_received_msg_id = details.extra.msg_id;
                        }
                    }
                    if (typeof details.extra.topic != 'undefined' && !details.topic) {
                        details.topic = details.extra.topic;
                    }
                } else {
                    details.extra = {
                        reconcile_mode: false
                    };
                }

                if (subscription.state != 'ready' && subscription.state != 'subscribed') { return; }

                details.topic = details.topic || subscription.topic;

                var action = {
                    subscription: subscription,
                    original_callback: original_callback,
                    args: args,
                    kwargs: kwargs,
                    details: details
                };


                if (WS.reconcile_mode.active && !details.extra.reconcile_mode) {
                    WS.reconcile_mode.queue.push(action);
                    return;
                }

                WS.run_callback(action);

            };
        }), // get_subscribe_callback

        run_callback: (function WS__run_callback (action) {
            if (action.details.extra.msg_id) {
                // TODO: big problem here, it means that we cannot run more than one callback
                // for the same publication, but it's exactly why we can have many subscriptions for
                // the same topic !! something has to be rewritten...
                if (action.details.extra.msg_id <= WS.last_msg_id) {
                    return;
                }
                WS.last_msg_id = action.details.extra.msg_id;
            }

            action.original_callback(
                action.details.topic,
                action.args,
                action.kwargs,
                action.subscription
            );
        }), // run_callback

        reconcile: (function WS__reconcile (last_received_id, next_received_id, iteration) {
            if (!last_received_id) {
                WS.after_reconcile();
                return;
            }

            var topics_rules = [];
            var added_rules = {};
            $.each(WS.subscriptions, function(topic, topic_subscriptions) {
                for (var i=0; i < topic_subscriptions.length; i++) {
                    var state = topic_subscriptions[i].state;
                    if (state == 'subscribed' || state == 'ready') {
                        var key = [topic, topic_subscriptions[i].match];
                        if (typeof added_rules[key] != 'undefined') { continue; }
                        topics_rules.push(key);
                        added_rules[key] = true;
                    }
                }
            });

            if (!topics_rules.length) {
                WS.after_reconcile();
                return;
            }

            iteration = iteration || 1;

            WS.session.call('gim.reconcile', [], {
                last_received_id: last_received_id,
                next_received_id: next_received_id || null,
                topics_rules: topics_rules,
                iteration: iteration
            }).then(
                function (result) {

                    if (result.error) {
                        WS.error_reconcile(result.error.message);
                        return;
                    }

                    var complete = false;
                    // Run the callbacks for events fired while we were offline
                    for (var i=0; i < result.missed_messages.length; i++) {
                        var entry = result.missed_messages[i],
                            details = {extra: entry.kwargs.ws_extra};

                        delete entry.kwargs.ws_extra;

                        // We can stop managing data received during reconcile if we also received
                        // the same messages in pubsub mode
                        if (WS.reconcile_mode.first_received_msg_id &&
                                details.extra.msg_id >= WS.reconcile_mode.first_received_msg_id) {
                            complete = true;
                            break;
                        }

                        // Go through all subscriptions for this message
                        for (var j=0; j < details.extra.subscribed.length; j++) {
                            var subscribed = details.extra.subscribed[j],
                                subscribed_topic = subscribed[0],
                                subscribed_match = subscribed[1],
                                topic_subscriptions = WS.subscriptions[subscribed_topic];

                            if (!topic_subscriptions || !topic_subscriptions.length) {
                                continue;
                            }

                            // Go through all the subscriptions for the topic
                            for (var k=0; k < topic_subscriptions.length; k++) {
                                var subscription = topic_subscriptions[j];
                                if (subscription.state != 'ready' && subscription.state != 'subscribed') {
                                    continue;
                                }
                                if (subscription.match != subscribed_match) {
                                    continue
                                }

                                // We have a match, we can call the callback
                                details.extra.reconcile_mode = true;
                                subscription.callback(entry.args, entry.kwargs, details);

                            } // for topic_subscriptions

                        } // for details.extra.subscribed

                    } // for result.missed_messages

                    if (!complete && result.max_msg_id < result.last_msg_id) {
                        WS.reconcile(result.max_msg_id, WS.reconcile_mode.first_received_msg_id, iteration+1);
                    } else {
                        WS.after_reconcile(result.last_msg_id);
                    }

                }, // then
                function () {
                    WS.error_reconcile();
                } // error
            );

        }), // reconcile

        start_reconcile: (function WS__start_reconcile () {
            WS.reconcile_mode.active = true;
            WS.reconcile_mode.queue = [];
            WS.reconcile_mode.first_received_msg_id = null;
        }), // start_reconcile

        after_reconcile: (function WS__after_reconcile (last_msg_id) {
            // Run the callbacks for events fired during the reconciliation
            // This works even if other are added during the loop because length is
            // recomputed each time
            for (var k=0; k < WS.reconcile_mode.queue.length; k++) {
                WS.run_callback(WS.reconcile_mode.queue[k]);
            }

            // The reconcile data included the very last message sent so if we didn't
            // receive more recent, we know it's the most recent one on the server (it
            // will reduce data to fetch for the next reconciliation)
            if (last_msg_id && last_msg_id > WS.last_msg_id) {
                WS.last_msg_id = last_msg_id;
            }

            // reconcile is done !
            WS.end_reconcile();

            WS.alert('Connected!<p>Real-time capabilities are enabled.</p>', 'ok', 1500, true);
            GithubNotifications.update_favicon(true);
        }), // after_reconcile

        end_reconcile: (function WS__end_reconcile () {
            WS.reconcile_mode.active = false;
            WS.reconcile_mode.queue = [];
            WS.reconcile_mode.first_received_msg_id = null;
        }), // end_reconcile

        error_reconcile: (function WS__error_reconcile (error_message) {
            if (!error_message) {
                error_message = 'There was a problem synchronizing data sent when you were offline.';
            }
            WS.alert(error_message + '<p>Real-time capabilities are disabled.</p><p>Please <a href="javascript:window.location.reload(true);">refresh the page</a>.</p>', 'ko', null, true);
            Favicon.set_val('×');
            WS.connection.close();
            WS.end_reconcile();
        }), // error_reconcile

        subscribe: (function WS__subscribe (topic, name, callback, match) {
            // Create topic entry if it doesn't exist
            if (typeof WS.subscriptions[topic] === 'undefined') {
                WS.subscriptions[topic] = [];
            }

            var subscription;

            var existing = $.grep(WS.subscriptions[topic], function(sub) {
                return (sub.name == name) && (sub.match == (match || 'exact')) && (
                    sub.state == 'subscribed' || sub.state == 'ready' || sub.state == 'unsubscribed'
                );
            });

            if (existing.length) {
                subscription = existing[0];
                switch (subscription.state) {
                    case 'subscribed':
                    case 'ready':
                        return;
                    case 'unsubscribed':
                        subscription.state = 'subscribed';
                        subscription.remote_id = null;
                }
            }

            if (!subscription) {
                var ws_args = {};
                if (match) {
                    ws_args.match = match;
                }

                // Prepare the subscription and add it locally
                subscription = {
                    topic: topic,
                    name: name,
                    callback: null,
                    // Will host the subscription id returned by the server
                    remote_id: null,
                    /* Valid states:
                      - subscribed: sub added locally, not on the server
                      - ready: added locally and on the server
                      - unsubscribed: removed locally and not on the server
                      - deleted: removed locally and on the server (can be removed from the list)
                     */
                    state: 'subscribed',
                    match: match || 'exact',
                    ws_args: ws_args
                };
                subscription.callback = WS.get_subscribe_callback(subscription, callback);
                WS.subscriptions[topic].push(subscription);
            }

            // Subscribe on the server if ready (if not, it will be done on the next connect)
            WS.subscribe_remotely(subscription);

        }), // subscribe

        subscribe_remotely: (function WS__subscribe_remotely (subscription) {
            if (!subscription.remote_id && WS.session && WS.session.isOpen) {
                WS.session.subscribe(subscription.topic, subscription.callback, subscription.ws_args).then(
                    function (remote_id) {
                        // We can now mark the subscription as subscribed locally and remotely
                        subscription.state = 'ready';
                        // And save the remote_id that will be used for the unsubscribe
                        subscription.remote_id = remote_id;
                    }
                );
            } // if session
        }), // subscribe_remotely

        subscribe_onconnect: (function WS__subscribe_onconnect () {

            // Arrange remote subscription to easier checks
            var remote = {};
            if (WS.session) {
                for (var i = 0; i < WS.session.subscriptions.length; i++) {
                    var topic_subscriptions = WS.session.subscriptions[i];
                    for (var j = 0; j < topic_subscriptions.length; j++) {
                        var subscription = topic_subscriptions[j];
                        if (typeof remote[subscription.topic] === 'undefined') {
                            remote[subscription.topic] = [];
                        }
                        remote[subscription.topic].push(subscription);
                    }
                }
            }

            $.each(WS.subscriptions, function(topic, topic_subscriptions) {

                // Stop if the connection is lost
                if (!WS.session || !WS.session.isOpen) { return false; }

                var remote_topic_subscriptions = [];
                if (typeof remote[topic] !== 'undefined') {
                    remote_topic_subscriptions = remote[topic];
                }

                for (var k=0; k < topic_subscriptions.length; k++) {
                    var subscription = topic_subscriptions[k];

                    // Mark as not subscribed remotely the one subscribed before we lost the
                    // connection and that are not subscribed remotely anymore
                    if (subscription.state == 'ready' && $.inArray(subscription.remote_id, remote_topic_subscriptions) == -1) {
                        subscription.state = 'subscribed';
                        subscription.remote_id = null;
                    }

                    // Subscribe remotely the one subscribed when WS was not connected, or marked
                    // above
                    if (subscription.state == 'subscribed') {
                        WS.subscribe_remotely(subscription);
                    }

                }

            });

        }), // subscribe_onconnect

        unsubscribe: (function WS__unsubscribe (topic, name) {
            // Do nothing if the topic doesn't exist
            if (typeof WS.subscriptions[topic] === 'undefined') { return; }

            for (var i=0; i < WS.subscriptions[topic].length; i++) {

                // Immediately invoked function to avoid closure+loop problem
                (function(subscription) {

                    var current_state = subscription.state;

                    if (current_state != 'subscribed' && current_state != 'ready') {
                        return;
                    }

                    if (!name || name && subscription.name == name) {
                        // Start by marking the subscription unsubscribed locally
                        subscription.state = 'unsubscribed';

                        // Unsubscribe remotely if it was subscribed remotely and we have a connection
                        // (if not, it will be done on the next connect
                        if (current_state == 'ready') {
                            WS.unsubscribe_remotely(subscription);
                        }

                    } // if name
                })(WS.subscriptions[topic][i]);

            } // for

        }), // unsubscribe

        unsubscribe_remotely: (function WS__unsubscribe_remotely (subscription) {
            if (subscription.remote_id && WS.session && WS.session.isOpen) {
                WS.session.unsubscribe(subscription.remote_id).then(
                    function() {
                        subscription.state = 'deleted';
                        subscription.remote_id = null;
                    }
                ); // then
            } // if session
        }), // unsubscribe_remotely

        unsubscribe_onconnect: (function WS__unsubscribe_onconnect () {

            $.each(WS.subscriptions, function(topic, topic_subscriptions) {

                // Stop if the connection is lost
                if (!WS.session || !WS.session.isOpen) { return false; }

                for (var i=0; i < topic_subscriptions.length; i++) {
                    var subscription = topic_subscriptions[i];
                    if (subscription.state != 'unsubscribed') { continue; }

                    WS.unsubscribe_remotely(subscription);
                }

            });

        }), // unsubscribe_onconnect

        receive_ping: (function WS__receive_ping (topic, args, kwargs) {
            if (kwargs.last_msg_id && !WS.reconcile_mode.active) {
                WS.last_msg_id = kwargs.last_msg_id;
            }
            if (kwargs.utcnow) {
                time_ago.update_start(kwargs.utcnow);
            }
            if (kwargs.software_version) {
                WS.check_software_version(kwargs.software_version);
            }
        }), // receive_ping

        check_software_version: (function WS__check_version (last_version) {
            if (last_version != window.software.version) {
                window.software.bad_version = true;
                try {
                    WS.connection.close();
                } catch (e) {}
                WS.alert_bad_version();
                setInterval(function() {
                    WS.alert_close();
                    setTimeout(WS.alert_bad_version, 1000);
                }, 15000);
            }
        }), // check_software_version

        alert_bad_version: (function WS__alert_bad_version () {
            WS.alert(window.software.name + ' was recently updated. Please <a href="javascript:window.location.reload(true);">reload the whole page</a>.', 'waiting');
            Favicon.set_val('↻');
        }), // alert_bad_version

        onchallenge: (function WS__onchallenge (session, method, extra) {
            if (method === 'wampcra') {
                return autobahn.auth_cra.sign(window.auth_keys.key2, extra.challenge);
            }
        }), // onchallenge

        onopen: (function WS__onopen (session) {
            if (WS.session) {
                WS.alert('Reconnecting for real-time capabilities...', 'waiting');
                Favicon.set_val('···');
            }
            WS.session = session;

            // Unsubscribe remotely all topics we unsubscribed locally while offline
            WS.unsubscribe_onconnect();
            // Mark the reconciliation as begun to not really run callback if we receive some data
            WS.start_reconcile();
            // Subscribe remotely all topics we subscribed locally while offline
            // But callbacks will not be executed until the reconciliation is done
            WS.subscribe_onconnect();
            // Run reconciliation to get all messages sent while offline
            WS.reconcile(WS.last_msg_id);
            // Now the reconciliation is over, all messages received while offline and during the
            // reconciliation where played.

            WS.subscribe('gim.ping', 'ping', WS.receive_ping);
        }), // onopen

        onclose: (function WS__onclose (reason, info) {
            if (info.message) {
                var parts = info.message.split('|');
                for (var i = 1; i < parts.length; i++) {
                    var part = parts[i];
                    if (part.indexOf('software_version=') == 0) {
                        WS.check_software_version(part.substring(17));
                    }
                }
            }
            if (window.software.bad_version) { return;}
            var message, timeout;
            switch (reason) {
                case 'closed':
                    timeout = 5000;  // to not display it if the page is closing
                    message = 'Connection closed!<p>Real-time capabilities are disabled.</p><p>Please <a href="javascript:window.location.reload(true);">refresh the page</a>.</p>';
                    break;
                case 'unsupported':
                    message = 'Connection cannot be opened!<p>Real-time capabilities are unsupported by your browser.</p>';
                    break;
                case 'unreachable':
                    message = 'Connection cannot be opened!<p>Real-time capabilities are disabled until the real-time server goes back.</p>';
                    break;
                default:
                    message = 'Connection lost!<p>Real-time capabilities are disabled until reconnect.</p>';
            }

            Favicon.set_val('×');
            if (timeout) {
                WS.alert_timer = setTimeout(function() { WS.alert(message, 'ko', null, true); }, timeout);
            } else {
                WS.alert(message, 'ko', null, true);
            }
        }), // onclose

        alert: (function WS__alert (html, mode, duration, allow_close) {

            if (mode == 'ko') {
                if (WS.alert_ko_done) { return; }
                WS.alert_ko_done = true;
            } else {
                WS.alert_ko_done = false;
            }

            if (WS.alert_timer) {
                clearTimeout(WS.alert_timer);
                WS.alert_timer = null;
            }

            WS.$alert.close.toggle(allow_close);
            WS.$alert.container.toggleClass('with-close', allow_close);

            WS.$alert.container.removeClass('ok ko waiting').addClass(mode+' visible');

            WS.$alert.message.html(html);

            if (duration) {
                WS.alert_timer = setTimeout(function() {
                    WS.$alert.container.removeClass('visible');
                }, duration);
            }
        }), // alert

        alert_close: (function WS__alert_close () {
            if (WS.alert_timer) {
                clearTimeout(WS.alert_timer);
                WS.alert_timer = null;
            }
            WS.$alert.container.removeClass('visible');
        }), // alert_close

        on_window_unload: (function WS__on_window_unload () {
            // avoid displaying the "disconnected" red box
            WS.alert_ko_done = true
        }), // on_window_unload

        init: (function WS__init () {
            if (!window.auth_keys.key1) {
                // no websocket if not authenticated
                return;
            }

            WS.$alert.message = WS.$alert.container.children('.message');
            WS.$alert.close = WS.$alert.container.children('.close');
            WS.$alert.close.on('click', WS.alert_close);
            WS.alert('Connecting for real-time capabilities...', 'waiting');
            Favicon.set_val('···');

            WS.URI = (window.location.protocol === "http:" ? "ws:" : "wss:") + "//" + window.WS_uri;
            WS.connection = new autobahn.Connection({
                url: WS.URI,
                realm: 'gim',
                authmethods: ["wampcra"],
                authid: window.auth_keys.key1,
                onchallenge: WS.onchallenge,
                max_retries: -1,
                max_retry_delay: 30,
                retry_delay_growth: 1.1,
                initial_retry_delay: 5
            });
            WS.connection.onopen = WS.onopen;
            WS.connection.onclose = WS.onclose;
            WS.connection.open();

            $(window).on('unload', WS.on_window_unload);

        }) // init
    }; // WS
    WS.init();
    window.WS = WS;


    var HistoryManager = {
        re_hash: new RegExp('^#(modal\-)?issue\-(\\d+)$'),
        previous_state: null,

        on_pop_state: function(ev) {
            var state = ev.state || history.state;
            if (!HistoryManager.on_history_pop_state(state)) {
                window.location.reload();
            }
            HistoryManager.previous_state = state;
        }, // on_pop_state

        on_history_pop_state: function (state) {
            if (state.body_id != body_id || state.main_repository_id != main_repository_id) {
                return false;
            }
            if (!HistoryManager.allow_load_url(state) || !HistoryManager.allow_load_issue(state)) {
                return false;
            }
            if (HistoryManager.is_url_changed(state)) {
                HistoryManager.load_url(state);
            }
            if (HistoryManager.is_issue_changed(state)) {
                HistoryManager.load_issue(state);
            }
            return true;
        }, // on_history_pop_state

        allow_load_url: function(state) {
            return true;
        }, // allow_load_url

        is_url_changed: function(state) {
            return !(
                HistoryManager.previous_state
                && HistoryManager.previous_state.body_id == state.body_id
                && HistoryManager.previous_state.main_repository_id == state.main_repository_id
                && HistoryManager.previous_state.url == state.url
            );
        }, // is_url_changed

        load_url: function(state) {
            if (IssuesList.all.length) {
                var $issues_list_node = IssuesList.all[0].$container_node;
                var $filters_node = $issues_list_node.prev(IssuesFilters.selector);
                IssuesFilters.reload_filters_and_list(state.url, $filters_node, $issues_list_node, true);
            }
        }, // load_url

        allow_load_issue: function(state) {
            return true;
        }, // allow_load_issue

        is_issue_changed: function(state) {
            return !(
                HistoryManager.previous_state
                && HistoryManager.previous_state.body_id == state.body_id
                && HistoryManager.previous_state.main_repository_id == state.main_repository_id
                && HistoryManager.previous_state.issue_id == state.issue_id
                && HistoryManager.previous_state.issue_in_modal == state.issue_in_modal
            );
        }, // is_issue_changed

        load_issue: function(state) {
            if (state.issue_id) {
                IssueDetail.open_issue_by_id(state.issue_id, !!state.issue_in_modal);
            } else {
                IssueDetail.clear_container(null, false);
                IssueDetail.hide_modal();
            }
        }, // load_issue

        get_issue_url_hash: function (issue_id, for_modal) {
            return '#' + (for_modal ? 'modal-' : '') + 'issue-' + issue_id;
        }, // get_issue_url_hash

        add_history: function (url, issue_id, issue_in_modal, replace) {
            if (!window.history || !window.history.pushState) { return; }

            var current_issue_id = null,
                current_issue_in_modal = null,
                current_hash = window.location.hash,
                current_url = UrlParser.remove_hash(window.location.href),
                final_url;

            if (current_hash && HistoryManager.re_hash.test(current_hash)) {
                var re_result = HistoryManager.re_hash.exec(current_hash);
                current_issue_id = re_result[2];
                current_issue_in_modal = !!re_result[1];
            }

            if (!issue_id) {
                if (issue_id === false) {
                    issue_id = null;
                    issue_in_modal = null;
                } else {
                    issue_id = current_issue_id;
                    issue_in_modal = current_issue_in_modal
                }
            } else {
                issue_in_modal = !!issue_in_modal;
            }

            if (!url) {
                url = current_url;
            } else {
                url = UrlParser.remove_hash(url);
            }

            if (issue_id == current_issue_id && issue_in_modal == current_issue_in_modal && url == current_url) {
                replace = true;
            }

            final_url = url;
            if (issue_id) {
                final_url += HistoryManager.get_issue_url_hash(issue_id, issue_in_modal);
            }

            HistoryManager.previous_state = {
                type: 'IssuesFilters',
                body_id: body_id,
                main_repository_id: main_repository_id,
                url: url,
                issue_id: issue_id,
                issue_in_modal: issue_in_modal
            };

            window.history[replace ? 'replaceState' : 'pushState'](HistoryManager.previous_state, $document.attr('title'), final_url);

        }, // add_history

        init: function() {
            window.onpopstate = HistoryManager.on_pop_state;
            HistoryManager.add_history(null, null, null, true);
        }
    }; // HistoryManager
    HistoryManager.init();
    window.HistoryManager = HistoryManager;


    var FilterManager = {
        lists_selector: '.issues-list:not(.no-filtering)',
        links_selector: 'a.js-filter-trigger',
        messages: {
            pr: {
                'on': 'Click to display only pull requests',
                'off': 'Click to stop displaying only pull requests'
            },
            merged: {
                'on': 'Click to display only merged pull requests',
                'off': 'Click to stop displaying only merged pull requests'
            },
            mergeable: {
                'on': 'Click to display only mergeable pull requests',
                'off': 'Click to stop displaying only mergeable pull requests'
            },
            checks: {
                'on': 'Click to display only pull requests with this checks status',
                'off': 'Click to stop displaying only pull requests with this checks status'
            },
            review: {
                'on': 'Click to display only pull requests with this review status',
                'off': 'Click to stop displaying only pull requests with this review status'
            },
            milestone: {
                'on': 'Click to filter on this milestone',
                'off': 'Click to stop filtering on this milestone'
            },
            labels: {
                'on': 'Click to filter on this ',
                'off': 'Click to stop filtering on this '
            },
            assigned: {
                'on': 'Click to filter issues assigned to them',
                'off': 'Click to stop filtering issues assigned to them'
            },
            created_by: {
                'on': 'Click to filter issues created by them',
                'off': 'Click to stop filtering issues created by them'
            },
            closed_by: {
                'on': 'Click to filter issues closed by them',
                'off': 'Click to stop filtering issues closed by them'
            },
            project: {
                'on': 'Click to filter on this project',
                'off': 'Click to stop filtering on this project'
            },
            project_column: {
                'on': "Click to filter on this project's column",
                'off': "Click to stop filtering on this project's column"
            }
        }, // messages
        block_empty_links: function(ev) {
            if ($(this).is(FilterManager.lists_selector + ' ' + FilterManager.links_selector)) {
                return Ev.cancel(ev);
            } else {
                return Ev.stop_event_decorate($.proxy(IssuesFilters.on_list_filter_click, this))(ev);
            }
        },
        update: function(index, link) {
            var $link = $(link),
                filter = $link.data('filter'),
                href, title;
            if (typeof this.cache[filter] === 'undefined') {
                var parts = filter.split(':'),
                    key = parts.shift(),
                    message_key = key,
                    value = parts.join(':'),
                    args = $.extend({}, this.args),
                    message_type;
                switch(key) {
                    case 'project_column':
                    case 'project':
                        value = (key == 'project' ? '__any__' : parts[1]);
                        key = 'project_' + parts[0];
                    case 'pr':
                    case 'merged':
                    case 'mergeable':
                    case 'checks':
                    case 'review':
                    case 'milestone':
                    case 'created_by':
                    case 'assigned':
                    case 'closed_by':
                        if (typeof args[key] === 'undefined' || args[key] != value) {
                            args[key] = value;
                            message_type = 'on';
                        } else {
                            delete args[key];
                            message_type = 'off';
                        }
                        title = FilterManager.messages[message_key][message_type];
                        href = Arg.url(this.path, args);
                        break;
                    case 'labels':
                        var labels = (args[key] || '').split(','),
                            pos = labels.indexOf(value),
                            final_labels = [];
                        if (pos >= 0) {
                            labels.splice(pos, 1);
                        } else {
                            labels.push(value);
                        }
                        for (var i = 0; i < labels.length; i++) {
                            if (labels[i]) { final_labels.push(labels[i]); }
                        }
                        if (final_labels.length) {
                            args[key] = final_labels.join(',');
                            message_type = 'on';
                        } else {
                            delete args[key];
                            message_type = 'off';
                        }
                        title = FilterManager.messages[message_key][message_type] + ($link.data('type-name') || 'label');
                        href = Arg.url(this.path, args);
                        break;
                }
                if (href) {
                    var orig_title = $link.attr('title') || '';
                    if (orig_title) { title = orig_title + '. ' + title}
                    this.cache[filter] = {href: href, title: title + '.'};
                }
            }
            if (typeof this.cache[filter] !== 'undefined') {
                $link.attr('href', this.cache[filter].href)
                     .attr('title', this.cache[filter].title)
                     .removeClass('js-filter-trigger');
            }
        }, // update
        convert_links: function(list) {
            var cache = {};
            list.$node.filter(FilterManager.lists_selector).find(FilterManager.links_selector)
                .on('click', FilterManager.block_empty_links)
                .each($.proxy(FilterManager.update, {cache: cache, args: Arg.parse(list.url), path: list.base_url}));
        } // convert_links
    }; // FilterManager


    var IssuesListIssue = (function IssuesListIssue__constructor (node, issues_list_group) {
        this.group = issues_list_group;
        var $node = $(node);
        this.set_issue_ident({
            number: $node.data('issue-number'),
            id: $node.data('issue-id'),
            repository: $node.data('repository'),
            repository_id: $node.data('repository-id')
        });
        this.prepare($node);
    }); // IssuesListIssue__constructor

    IssuesListIssue.selector = '.issue-item';
    IssuesListIssue.link_selector = '.issue-link';

    IssuesListIssue.prototype.prepare = (function IssuesListIssue__prepare (node, selected) {
        var i, href, project_number, column_id_and_card_position, $node;
        if (node.jquery) {
            $node = node;
            node = $node[0];
        } else {
            $node = $(node);
        }
        this.node = node;
        this.node.IssuesListIssue = this;
        this.$node = $node;
        this.$link = this.$node.find(IssuesListIssue.link_selector);
        if (this.$link.length) {
            href = this.$link.attr('href').split("#")[0].split('?')[0] + '?referer=' + encodeURIComponent(window.location.href.split("#")[0]);
            this.$link.attr('href', href);
        }
        this.created_at = this.$node.data('created_at');
        this.updated_at = this.$node.data('updated_at');
        this.project_numbers = (''+(this.$node.data('projects') || '')).split(',').filter(function(number){ return number;}).map(function(number){ return parseInt(number, 10)});
        this.project_positions = {};
        for (i = 0; i < this.project_numbers.length; i++) {
            project_number = this.project_numbers[i];
            column_id_and_card_position = this.$node.data('project_' + project_number + '-position').split(':');
            this.project_positions[project_number] = {
                'column_id': parseInt(column_id_and_card_position[0], 10),
                'card_position': parseInt(column_id_and_card_position[1], 10)
            };
        }
        if (this.group && this.is_real_issue()) {
            this.toggle_selectable(undefined, selected);
        }
    }); // IssuesListIssue__prepare

    IssuesListIssue.prototype.set_issue_ident = (function IssuesListIssue__set_issue_ident (issue_ident) {
        this.issue_ident = issue_ident;
        this.number = issue_ident.number;
        this.id = issue_ident.id;
        this.repository = issue_ident.repository;
        this.repository_id = issue_ident.repository_id;
    }); // IssuesListIssue__set_issue_ident

    IssuesListIssue.prototype.is_real_issue = (function IssuesList__is_real_issue () {
        return parseInt(this.id) == this.id;
    }); // IssuesList__is_real_issue

    IssuesListIssue.on_issue_node_event = (function IssuesListIssue_on_issue_node_event (issue_method, stop, pass_event) {
        var decorator = function(e) {
            // ignore filter links
            if (e.target.nodeName.toUpperCase() == 'A' && e.target.className.indexOf('issue-link') == -1 || e.target.parentNode.nodeName.toUpperCase() == 'A') { return; }

            var issue_node = $(e.target).closest(IssuesListIssue.selector);
            if (!issue_node.length || !issue_node[0].IssuesListIssue) { return; }
            if (pass_event) {
                return issue_node[0].IssuesListIssue[issue_method](e);
            } else {
                return issue_node[0].IssuesListIssue[issue_method]();
            }
        };
        return stop ? Ev.stop_event_decorate(decorator) : decorator;
    }); // IssuesListIssue_on_issue_node_event

    IssuesListIssue.on_current_issue_key_event = (function IssuesListIssue_on_current_issue_key_event (issue_method, param, ignore_if_dropdown) {
        var decorator = function(ev) {
            if (ignore_if_dropdown && $(ev.target).closest('.dropdown-menu').length) { return; }
            if (!IssuesList.current) { return; }
            if (!IssuesList.current.current_group) { return; }
            if (!IssuesList.current.current_group.current_issue) { return; }
            return IssuesList.current.current_group.current_issue[issue_method](param);
        };
        return Ev.key_decorate(decorator);
    }); // IssuesListIssue_on_current_issue_key_event

    IssuesListIssue.init_events = (function IssuesListIssue_init_events () {
        $document.on('click', IssuesListIssue.selector, IssuesListIssue.on_issue_node_event('on_click', true, true));
        jwerty.key('↩', IssuesListIssue.on_current_issue_key_event('open', true, true));
        jwerty.key('space', IssuesListIssue.on_current_issue_key_event('on_space_key', false, true));
        jwerty.key('shift+space', IssuesListIssue.on_current_issue_key_event('on_space_key', true, true));
        jwerty.key('x', IssuesListIssue.on_current_issue_key_event('on_x_key_to_select', false, true));
        jwerty.key('shift+x', IssuesListIssue.on_current_issue_key_event('on_x_key_to_select', true, true));
        $document.on('ifChecked ifUnchecked ifToggled', IssuesListIssue.selector + ' .selector input', IssuesListIssue.on_selector_toggled);
    });

    IssuesListIssue.prototype.open = (function IssuesListIssue__open (ev) {
        this.get_html_and_display ();
        return false; // stop event propagation
    }); // IssuesListIssue__open

    IssuesListIssue.prototype.on_space_key = (function IssuesListIssue__on_space_key (shift) {
        if (this.$node.hasClass('selectable')) {
            return this.on_x_key_to_select(shift);
        } else if (!shift) {
            return this.toggle_details();
        }
    }); // IssuesListIssue__on_space_key

    IssuesListIssue.prototype.toggle_details = (function IssuesListIssue__toggle_details () {
        this.$node.toggleClass('details-toggled');
        return false; // stop event propagation
    }); // IssuesListIssue__toggle_details

    IssuesListIssue.prototype.on_click = (function IssuesListIssue__on_click (ev) {
        if ($(ev.target).is(':button,:input')) {
            this.set_current(true);
            return;
        }
        if (ev.ctrlKey) {
            return this.toggle_details();
        } else if (ev.shiftKey) {
            this.get_html_and_display (null, true);
        } else {
            this.set_current(true);
            if (!IssueDetail.$main_container.length) {
                this.get_html_and_display (null, true);
            }
        }
        return false; // stop event propagation
    }); // IssuesListIssue__on_click

    IssuesListIssue.prototype.unset_current = (function IssuesListIssue__unset_current () {
        this.group.current_issue = null;
        this.$node.removeClass('active');
    }); // IssuesListIssue__unset_current

    IssuesListIssue.prototype.set_current = (function IssuesListIssue__set_current (propagate, force_load, no_loading, keep_recent, nofocus) {
        if (IssueDetail.$main_container.length || force_load) {
            this.get_html_and_display(null, null, force_load, no_loading);
        }
        if (!this.group.no_visible_issues) {
            if (propagate) {
                this.group.list.set_current();
                this.group.set_current(null, nofocus);
            }
            if (this.group.current_issue) {
                this.group.current_issue.unset_current();
            }
            this.group.current_issue = this;
            this.group.unset_active();
            if (!keep_recent) { this.$node.removeClass('recent'); }
            this.$node.addClass('active');
            var issue = this;
            if (this.group.collapsed) {
                this.group.open(false, nofocus ? null : function() { issue.$link.focus(); });
            } else if (!nofocus && this.$link.length) {
                this.$link.focus();
            }
        }
    }); // IssuesListIssue__set_current

    IssuesListIssue.prototype.get_html_and_display = (function IssuesListIssue__get_html_and_display (url, force_popup, force_load, no_loading) {
        if (!url && !this.$link.length) {
            return;
        }
        var container = IssueDetail.get_container_waiting_for_issue(this.issue_ident, force_popup, force_load);
        if (!container) {
            return;
        }
        var is_popup = !!(force_popup || container.$window);
        if (!url) { url = this.$link.attr('href').split("#")[0]; }
        if (!no_loading) {
            IssueDetail.set_container_loading(container);
        } else {
            IssueDetail.unset_issue_waypoints(container.$node);
        }
        if (is_popup) {
            IssueDetail.show_modal();
        }
        $.ajax({
            url: url,
            success: is_popup ? this.display_html_in_popup : this.display_html,
            error: is_popup ? this.error_getting_html_in_popup: this.error_getting_html,
            context: this
        });
    }); // IssuesListIssue__get_html_and_display

    IssuesListIssue.prototype.display_html = (function IssuesListIssue__display_html (html) {
        IssueDetail.display_issue(html, this.issue_ident, false);
    }); // IssuesListIssue__display_html

    IssuesListIssue.prototype.display_html_in_popup = (function IssuesListIssue__display_html_in_popup (html) {
        IssueDetail.display_issue(html, this.issue_ident, true);
    }); // IssuesListIssue__display_html_in_popup

    IssuesListIssue.prototype.error_getting_html = (function IssuesListIssue__error_getting_html (xhr) {
        IssueDetail.clear_container('error ' + xhr.status, false);
    }); // IssuesListIssue__error_getting_html

    IssuesListIssue.prototype.error_getting_html_in_popup = (function IssuesListIssue__error_getting_html_in_popup (xhr) {
        var container = IssueDetail.get_container(true);
        IssueDetail.unset_issue_waypoints(container.$node);
        container.$window.removeClass('full-screen');
        container.$node.removeClass('big-issue');
        IssueDetail.fill_container(container,
            '<div class="alert alert-error"><p>Unable to get the issue. Possible reasons are:</p><ul>'+
                '<li>You are not allowed to see this issue</li>' +
                '<li>This issue is not on a repository you subscribed on ' + window.software.name + '</li>' +
                '<li>The issue may have been deleted</li>' +
                '<li>Connectivity problems</li>' +
            '</ul></div>');
    }); // IssuesListIssue__error_getting_html_in_popup

    IssuesListIssue.open_issue = (function IssuesListIssue_open_issue (issue_ident, force_popup, force_load, no_loading) {
        var issue = IssuesList.get_issue_by_ident(issue_ident);
        if (issue) {
            if (force_popup) {
                issue.get_html_and_display(null, true, force_load, no_loading);
            } else {
                issue.set_current(true, force_load, no_loading);
            }
        } else {
            var url = IssueDetail.get_url_for_ident(issue_ident);
            issue = new IssuesListIssue({}, null);
            issue.set_issue_ident(issue_ident);
            issue.get_html_and_display(url, force_popup, force_load, no_loading);
        }
    }); // IssuesListIssue_open_issue

    IssuesListIssue.finalize_alert = (function IssuesListIssue__finalize_alert ($issue_node, kwargs, front_uuid_exists, $data, $containers, message_mode, message_conf) {
        var with_repository = $data
                                ? $data.hasClass('with-repository') || ($data.data('repository') &&  $data.data('repository') != main_repository)
                                : (
                                    $issue_node ? $issue_node.hasClass('with-repository') : false
                                ),
            with_notification = $data
                                    ? $data.hasClass('with-notification')
                                    : (
                                        $issue_node ? $issue_node.hasClass('with-notification') : false
                                    ),
            display_repository = (with_repository || with_notification)
                                    ? (
                                        $data
                                            ? $data.data('repository')
                                            : (
                                                $issue_node ? $issue_node.data('repository') : ''
                                            )
                                    )
                                    : '',
            text, $message, issue_type = kwargs.is_pr ? 'pull request' : 'issue';

        if ($issue_node && with_notification) {
            GithubNotifications.init_item_forms();
        }

        if (!kwargs.front_uuid || !front_uuid_exists) {

            $containers = $containers || IssueDetail.get_containers_for_ident({'id': kwargs.id});

            if ($containers.length) {
                IssueDetail.mark_containers_nodes_as_updated($containers, issue_type);
            }

            if (!message_conf.done) {
                message_conf.done = true;

                if ($containers.length) {
                    text = 'The current ' + issue_type + ' ' + display_repository + '#' + kwargs.number + ' was just updated';
                    if (!message_conf.no_extended_message) {
                        if (message_mode == 'removed') {
                            text += ' and does not match your filter anymore';
                        } else if (message_mode == 'hidden') {
                            text += ' and does not match your filter';
                        } else if (message_mode == 'added') {
                            text += ' and now matches your filter';
                        }
                    }
                    $message = $('<span>' + text + '.</span>');
                } else {
                    text = 'The following ' + issue_type + ' was just ' + (kwargs.is_new ? 'created' : 'updated');
                    if (!message_conf.no_extended_message) {
                        if (message_mode == 'removed') {
                            text += ' and does not match your filter' + (kwargs.is_new ? '' : ' anymore');
                        } else if (message_mode == 'hidden') {
                            text += ' and does not match your filter';
                        } else if (message_mode == 'added') {
                            text += (kwargs.is_new ? ' and' : ' and now') + ' matches your filter';
                        }
                    }
                    $message = $('<span>' + text + ':<br /></span>');
                    $message.append($('<span style="font-weight: bold"/>').text(display_repository + $issue_node.find('.issue-link').text()));
                }

                MessagesManager.add_messages([MessagesManager.make_message($message, 'info')]);
            }

        } else if (kwargs.front_uuid && kwargs.is_new && front_uuid_exists) {
            IssueDetail.refresh_created_issue(kwargs.front_uuid);
        }
    }); // IssuesListIssue__finalize_alert

    IssuesListIssue.prototype.remove_from_project = (function IssuesListIssue__remove_from_project (project_number) {
        var pp = this.project_positions, project_numbers_str, project_position_key;
        if (pp[project_number]) {
            delete pp[project_number];
            this.project_numbers.splice(this.project_numbers.indexOf(project_number), 1);
            if (!this.project_numbers.length) {
                this.$node.removeData('projects');
                this.$node.removeAttr('data-projects');
            } else {
                project_numbers_str = this.project_numbers.join(',');
                this.$node.data('projects', project_numbers_str);
                this.$node.attr('data-projects', project_numbers_str);
            }
            project_position_key = 'project_' + project_number + '-position';
            this.$node.removeData(project_position_key);
            this.$node.removeAttr('data-' + project_position_key);
        }
    }); // IssuesListIssue__remove_from_project

    IssuesListIssue.prototype.move_to_project_column = (function IssuesListIssue__move_to_project_column (project_number, column_id, position) {
        var pp = this.project_positions, project_numbers_str, project_position_str, project_position_key;
        if (!pp[project_number]) {
            pp[project_number] = {};
            this.project_numbers.push(project_number);
            project_numbers_str = this.project_numbers.join(',');
            this.$node.data('projects', project_numbers_str);
            this.$node.attr('data-projects', project_numbers_str);
        }
        pp[project_number].column_id = column_id;
        pp[project_number].card_position = position;
        project_position_str = column_id + ':' + position;
        project_position_key = 'project_' + project_number + '-position';
        this.$node.data(project_position_key, project_position_str);
        this.$node.attr('data-' + project_position_key, project_position_str);
    }); // IssuesListIssue__move_to_project_column

    IssuesListIssue.prototype.on_update_card_alert = (function IssuesListIssue__on_update_card_alert (topic, args, kwargs) {
        var same_column = false;
        if (kwargs.project_number && kwargs.column_id && this.project_positions) {
            same_column = (this.project_positions[kwargs.project_number] && this.project_positions[kwargs.project_number].column_id == kwargs.column_id);
            this.move_to_project_column(kwargs.project_number, kwargs.column_id, kwargs.position);
            this.group.ask_for_reorder();
        }
        return same_column;
    }); // IssuesListIssue__on_update_card_alert

    IssuesListIssue.prototype.on_update_alert = (function IssuesListIssue__on_update_alert (topic, args, kwargs, message_conf) {
        var existing_hash = this.$node.data('issue-hash'), issue=this,
            front_uuid_exists = UUID.exists(kwargs.front_uuid);

        if (!kwargs.hash || kwargs.hash == existing_hash) {
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                UUID.set_state(kwargs.front_uuid, '');
            }
            delete IssuesList.updating_ids[kwargs.id];
            return;
        }

        $.get(kwargs.url + '?referer=' + window.encodeURIComponent(issue.group.list.url)).done(function(data) {
            var $data = $(data),
                $containers = IssueDetail.get_containers_for_ident({'id': kwargs.id}),
                group = issue.group,
                is_issue_active = issue.$node.hasClass('active'),
                is_group_active = issue.group.$node.hasClass('active'),
                is_group_current = group.is_current(),
                is_selected = issue.is_selected();

            if (!$containers.length && (!kwargs.front_uuid || !front_uuid_exists)) { $data.addClass('recent'); }
            if (is_issue_active) { $data.addClass('active'); }

            issue.$node.replaceWith($data);
            issue.prepare(issue.group.$node.find(IssuesListIssue.selector + '[data-issue-id=' + kwargs['id'] + ']')[0], is_selected);

            // check if we have to change group
            var list = issue.group.list,
                same_group = true;
            if (list.group_by_key) {
                var filter = issue.get_filter_for(list.group_by_key);
                group = list.get_group_for_value(filter.value) || list.create_group(filter.value, filter.text, filter.description);
                if (group != issue.group) {
                    same_group = false;
                    issue.move_to_group(group);
                    if (!$containers.length && (!kwargs.front_uuid || !front_uuid_exists)) {
                        group.$node.addClass('recent');
                    }
                }
            }

            if (same_group) {
                group.ask_for_reorder();
                list.ask_for_quicksearch_results_reinit();
            }
            if (is_group_current) { group.set_current(is_group_active, true); }
            if (is_issue_active) { issue.set_current(null, null, null, true, true); }

            FilterManager.convert_links(list);
            IssuesListIssue.finalize_alert(issue.$node, kwargs, front_uuid_exists, $data, $containers, 'updated', message_conf);

        }).fail(function(response) {
            if (response.status == 404) {
                if (issue.group) { issue.group.remove_issue(issue); }
                IssuesListIssue.finalize_alert(issue.$node, kwargs, front_uuid_exists, null, null, 'removed', message_conf);
            }
        }).always(function() {
            message_conf.on_list_done();
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                UUID.set_state(kwargs.front_uuid, '');
            }
            delete IssuesList.updating_ids[kwargs.id];
        });
    }); // IssuesListIssue__on_update_alert

    IssuesListIssue.get_data_for_node = (function IssuesListIssue_get_data_for_node (node) {
        var $this = node.jquery ? node : $(this);
        return {$node: $this, filters: $this.data()};
    }); // IssuesListIssue__get_data_for_node

    IssuesListIssue.prototype.get_nodes_with_filter = (function IssuesListIssue__get_filters () {
        var result = $.makeArray(this.$node.find('[data-filter]').map(IssuesListIssue.get_data_for_node)),
            self_result = IssuesListIssue.get_data_for_node(this.$node);
        if (self_result.filters.filter) {
            result.unshift(self_result);
        }
        return result;
    }); // IssuesListIssue__get_filters

    IssuesListIssue.prototype.get_filter_for = (function IssuesListIssue__get_filter_for (filter_key) {
        var searchable_filter, matching_filters, filter_value, filter_text, filter_description,
            filters_nodes = this.get_nodes_with_filter();

        if (filter_key.indexOf('label_type:') == 0) {
            // specific case of issues grouped by a LabelType
            searchable_filter = filter_key.substring(11);
            matching_filters = $.grep(filters_nodes, function(filtered_node) { return filtered_node.filters.typeId == searchable_filter; });
            if (matching_filters.length) { // we have a filter that matches the group!
                filter_value = matching_filters[0].filters.filter.substring(7);  // remove 'labels:' prefix
                filter_text = matching_filters[0].$node.contents()[1].textContent;
            } else {
                filter_value = '';
            }
        } else {
            // standard group-by
            searchable_filter = filter_key + ':';
            matching_filters = $.grep(filters_nodes, function(filtered_node) { return filtered_node.filters.filter.indexOf(searchable_filter) == 0; });
            if (matching_filters.length) { // we have a filter that matches the group!
                filter_value = matching_filters[0].filters.filter.substring(searchable_filter.length);
                if (filter_key == 'milestone') {
                    filter_text = matching_filters[0].$node.contents()[1].textContent;
                } else if (filter_key == 'reason') {
                    try {
                        filter_text = matching_filters[0].$node.contents()[0].textContent;
                    } catch(e) {
                        filter_text = filter_value;
                    }
                    filter_description = matching_filters[0].$node.attr('title_all');
                } else if (filter_key == 'pr') {
                    filter_text = filter_value == 'no' ? 'issues' : 'pull-requests';
                } else if (filter_key == 'active') {
                    filter_text = filter_value == 'no' ? 'inactive' : 'active';
                } else if (filter_key == 'unread') {
                    filter_text = filter_value == 'no' ? 'read' : 'unread';
                } else if (filter_key == 'project_column') {
                    filter_text = matching_filters[0].$node.parent().text();
                } else if (filter_key == 'project') {
                    filter_text = matching_filters[0].$node.contents()[1].textContent;
                } else {
                    filter_text = filter_value;
                }
            } else {
                filter_value = '__none__';
            }
        }
        return {value: filter_value, text: filter_text, description: filter_description};
    });  // IssuesListIssue__get_filter_for

    IssuesListIssue.prototype.move_to_group = (function IssuesListIssue__move_to_group (new_group) {
        var orig_group = this.group,
            orig_list = orig_group.list,
            new_list = new_group.list;

        var index = orig_group.issues.indexOf(this);
        if (index > -1) {
            orig_group.issues.splice(index, 1);
        }
        new_group.add_issue(this, true);
        if (!orig_group.issues.length) {
            orig_list.remove_group(orig_group);
        } else {
            new_list.ask_for_quicksearch_results_reinit();
            orig_group.ask_for_filtered_issues_update();
        }
    }); // IssuesListIssue__move_to_group

    IssuesListIssue.prototype.clean = (function IssuesListIssue__clean () {
        this.node.IssuesListIssue = null;
        this.$node.remove();
        this.$node = null;
        this.node = null;
        this.group = null;
    }); // IssuesListIssue__clean

    IssuesListIssue.prototype.get_sort_value = (function IssuesListIssue__get_sort_value () {
        var sort_field = this.group.list.sort_field;
        switch (sort_field) {
            case 'updated':
            case 'created':
                return this[sort_field+'_at'];
            case 'position':
                var project_number = this.group.group_by_value ? this.group.group_by_values[0] : this.group.list.filtered_project_number;
                if (this.project_positions[project_number]) {
                    return this.project_positions[project_number].card_position;
                }
                return 99999;
        }

        return null;
    }); // IssuesListIssue__get_sort_value

    IssuesListIssue.prototype.toggle_selectable = (function IssuesListIssue__toggle_selectable(activated, selected) {
        if (!this.is_real_issue()) { return; }
        if (typeof activated == 'undefined') {
            activated = this.group.list.$container_node.hasClass('multiselect-mode');
        }
        this.$node.toggleClass('selectable', activated);
        if (activated) {
            if (this.$node.children('.selector').length) { return; }
            var $selector = $('<div class="selector not-hoverable"><input type="checkbox" value="' + this.issue_ident.id + '" />');
            this.$node.prepend($selector);
            var $input = $selector.find('input');
            $input.iCheck({checkboxClass: 'icheckbox_flat-blue'});
            $selector.find('.iCheck-helper').off('mouseover mouseout').on('mousedown keydown', IssuesListIssue.on_selector_icheck_helper_action_start);
            if (selected) {
                $input.iCheck('check');
            }
            this.group.list.ask_for_selected_count_update();
        } else {
            this.$node.children('.selector').remove();
        }
    }); // IssuesListIssue__toggle_selectable

    IssuesListIssue.prototype.on_x_key_to_select = (function IssuesListIssue__on_x_key_to_select (shift) {
        this.toggle_selected(undefined, !!shift);
        return false;
    }); // IssuesListIssue__on_x_key_to_select

    IssuesListIssue.on_selector_icheck_helper_action_start = (function IssuesListIssue_on_selector_icheck_helper_action_start(ev) {
        var $input = $(this).prev();
        $input.data('shift-used', ev.shiftKey);
        var issue = $input.closest(IssuesListIssue.selector)[0].IssuesListIssue;
    }); // IssuesListIssue_on_selector_icheck_helper_action_start

    IssuesListIssue.prototype.is_selected = (function IssuesListIssue__is_selected() {
        if (!this.$node.hasClass('selectable')) { return false; }
        return this.$node.find('.selector input').prop('checked');
    }); // IssuesListIssue__is_selected

    IssuesListIssue.on_selector_toggled = function(ev) {
        var $input = $(this),
            shift = $input.data('shift-used'),
            issue = $input.closest(IssuesListIssue.selector)[0].IssuesListIssue,
            selected, issues;
        $input.data('shift-used', null);
        if (shift) {
            selected = $input.prop('checked');
            issues = issue.group.list.get_issues_between(issue.group.list.last_directly_touched_selectable_issue, issue);
            for (var i = 0; i < issues.length; i++) {
                issues[i].toggle_selected(selected, null);
            }
        }
        issue.group.list.last_directly_touched_selectable_issue = issue;
        issue.group.list.ask_for_selected_count_update();
    };

    IssuesListIssue.prototype.toggle_selected = (function IssuesListIssue__toggle_selected (selected, shift) {
        if (!this.is_real_issue()) { return; }
        if (!this.$node.hasClass('selectable')) { return; }
        var action = typeof selected == 'undefined' ? 'toggle' : (selected ? 'check' : 'uncheck'),
            $input = this.$node.find('.selector input');
        $input.data('shift-used', shift);
        $input.iCheck(action);
    }); // IssuesListIssue__toggle_selected

    var IssuesListGroup = (function IssuesListGroup__constructor (node, issues_list) {
        this.list = issues_list;

        this.node = node;
        this.node.IssuesListGroup = this;
        this.$node = $(node);
        this.$link = this.$node.find(IssuesListGroup.link_selector);
        this.$issues_node = this.$node.find(IssuesListGroup.issues_list_selector);
        this.$count_node = this.$node.find('.issues-count');

        this.group_by_value = this.$node.data('group_by-value');
        this.group_by_values = this.group_by_value ? (''+this.group_by_value).split(':') : [];

        this.collapsable = this.$issues_node.hasClass('collapse');
        this.collapsed = this.collapsable && !this.$issues_node.hasClass('in');

        this.reorder_counter = 0;
        this.update_filtered_issues_counter = 0;

        var group = this;
        this.issues = $.map(this.$node.find(IssuesListIssue.selector),
                    function(node) { return new IssuesListIssue(node, group); });
        this.filtered_issues = this.issues;
        this.current_issue = null;

        this.no_visible_issues = this.filtered_issues.length === 0;
    }); // IssuesListGroup__constructor

    IssuesListGroup.selector = '.issues-group:not(.template)';
    IssuesListGroup.template_selector = '.issues-group.template';
    IssuesListGroup.link_selector = '.box-header';
    IssuesListGroup.issues_list_selector = '.issues-group-issues';

    IssuesListGroup.prototype.unset_active = (function IssuesListGroup__unset_active () {
        this.$node.removeClass('active');
    }); // IssuesListGroup__unset_active

    IssuesListGroup.prototype.set_active = (function IssuesListGroup__set_active (nofocus) {
        if (this.current_issue) {
            this.current_issue.unset_current();
        }
        IssueDetail.clear_container();
        this.$node.addClass('active');
        if (!nofocus) { this.$link.focus(); }
    }); // IssuesListGroup__set_active

    IssuesListGroup.prototype.unset_current = (function IssuesListGroup__unset_current () {
        this.unset_active();
        if (this.current_issue) {
            this.current_issue.unset_current();
        }
        this.list.current_group = null;
    }); // IssuesListGroup__set_current

    IssuesListGroup.prototype.is_current = (function IssuesListGroup__is_current () {
        return this.list.current_group == this;
    }); // IssuesListGroup__is_current

    IssuesListGroup.prototype.set_current = (function IssuesListGroup__set_current (active, nofocus) {
        if (this.list.current_group) {
            this.list.current_group.unset_current();
        }
        this.list.current_group = this;
        if (active) {
            this.set_active(nofocus);
        }
    }); // IssuesListGroup__set_current

    IssuesListGroup.prototype.open = (function IssuesListGroup__open (set_active, on_shown_callback) {
        if (!this.collapsable || !this.collapsed || this.no_visible_issues) { return ; }
        if (set_active) { this.set_active(); }
        if (on_shown_callback) {
            var group = this,
                on_shown = function() {
                    group.$issues_node.off('shown.collapse', on_shown);
                    on_shown_callback();
                };
            this.$issues_node.on('shown.collapse', on_shown);
        }
        this.$issues_node.collapse('show');
        return false; // stop event propagation
    }); // IssuesListGroup__open

    IssuesListGroup.prototype.close = (function IssuesListGroup__close (set_active) {
        if (!this.collapsable || this.collapsed || this.no_visible_issues) { return; }
        if (set_active) { this.set_active(); }
        this.$issues_node.collapse('hide');
        return false; // stop event propagation
    }); // IssuesListGroup__close

    IssuesListGroup.prototype.toggle = (function IssuesListGroup__toggle (set_active) {
        if (!this.collapsable || this.no_visible_issues) { return; }
        return this.collapsed ? this.open(set_active) : this.close(set_active);
    }); // IssuesListGroup__toggle

    IssuesListGroup.on_group_node_event = (function IssuesListGroup_on_group_node_event (group_method, stop) {
        var decorator = function(e) {
            var group_node = $(e.target).closest(IssuesListGroup.selector);
            if (!group_node.length || !group_node[0].IssuesListGroup) { return; }
            return group_node[0].IssuesListGroup[group_method]();
        };
        return stop ? Ev.stop_event_decorate(decorator): decorator;
    }); // IssuesListGroup_on_group_node_event

    IssuesListGroup.on_current_group_key_event = (function IssuesListGroup_on_current_group_key_event (group_method, param) {
        var decorator = function() {
            if (!IssuesList.current) { return; }
            if (!IssuesList.current.current_group) { return; }
            return IssuesList.current.current_group[group_method](param);
        };
        return Ev.key_decorate(decorator);
    }); // IssuesListGroup_on_current_group_key_event

    IssuesListGroup.init_events = (function IssuesListGroup_init_events () {
        $document.on('click', IssuesListGroup.link_selector, IssuesListGroup.on_group_node_event('on_click', true));
        $document.on('show.collapse', IssuesListGroup.issues_list_selector, IssuesListGroup.on_group_node_event('on_show'));
        $document.on('hide.collapse', IssuesListGroup.issues_list_selector, IssuesListGroup.on_group_node_event('on_hide'));
        jwerty.key('o/→', IssuesListGroup.on_current_group_key_event('open', true));
        jwerty.key('c/←', IssuesListGroup.on_current_group_key_event('close', true));
        jwerty.key('t', IssuesListGroup.on_current_group_key_event('toggle'));
        jwerty.key('⇞', IssuesListGroup.on_current_group_key_event('go_to_first_issue_if_opened'));
        jwerty.key('⇟', IssuesListGroup.on_current_group_key_event('go_to_last_issue_if_opened'));
    });

    IssuesListGroup.prototype.on_click = (function IssuesListGroup__on_click () {
        this.list.set_current();
        this.set_current(true);
        this.toggle(true);
        return false; // stop event propagation
    }); // IssuesListGroup__on_click

    IssuesListGroup.prototype.go_to_previous_item = (function IssuesListGroup__go_to_previous_item () {
        if (this.collapsed || this.no_visible_issues) { return; }
        // if we have no current issue, abort
        if (!this.current_issue) { return; }
        // try to select the previous issue
        var previous_issue = this.get_previous_issue();
        if (previous_issue) {
            previous_issue.set_current();
        } else {
            // no previous issue, select the current group itself
            this.set_active();
        }
        return false; // stop event propagation
    }); // IssuesListGroup__go_to_previous_item

    IssuesListGroup.prototype.go_to_next_item = (function IssuesListGroup__go_to_next_item () {
        if (this.collapsed || this.no_visible_issues) { return; }
        // if we have no current issue, select the first issue if we have one
        if (!this.current_issue) {
            if (!this.filtered_issues.length) { return; }
            this.filtered_issues[0].set_current();
            return false; // stop event propagation
        }
        // try to select the next issue
        var next_issue = this.get_next_issue();
        if (!next_issue) { return; }
        next_issue.set_current();
        return false; // stop event propagation
    }); // IssuesListGroup__go_to_next_item

    IssuesListGroup.prototype.go_to_first_issue = (function IssuesListGroup__go_to_first_issue (propagate) {
        if (this.collapsed || this.no_visible_issues) { return; }
        this.filtered_issues[0].set_current(propagate);
        return false; // stop event propagation
    }); // IssuesListGroup__go_to_first_issue

    IssuesListGroup.prototype.go_to_first_issue_if_opened = (function IssuesListGroup__go_to_first_issue_if_opened (propagate) {
        if (!this.current_issue) { return; }
        return this.go_to_first_issue(propagate);
    }); // IssuesListGroup__go_to_first_issue_if_opened

    IssuesListGroup.prototype.go_to_last_issue = (function IssuesListGroup__go_to_last_issue (propagate) {
        if (this.collapsed || this.no_visible_issues) { return; }
        this.filtered_issues[this.filtered_issues.length-1].set_current(propagate);
        return false; // stop event propagation
    }); // IssuesListGroup__go_to_last_issue

    IssuesListGroup.prototype.go_to_last_issue_if_opened = (function IssuesListGroup__go_to_last_issue_if_opened (propagate) {
        if (!this.current_issue) { return; }
        return this.go_to_last_issue(propagate);
    }); // IssuesListGroup__go_to_last_issue_if_opened

    IssuesListGroup.prototype.get_previous_issue = (function IssuesListGroup__get_previous_issue (all, issue) {
        if (!issue) { issue = this.current_issue; }
        if (!issue) { return false; }
        var issues = all ? this.issues : this.filtered_issues;
        var pos = issues.indexOf(issue);
        if (pos < 1) { return null; }
        return issues[pos - 1];
    }); // IssuesListGroup__get_previous_issue

    IssuesListGroup.prototype.get_next_issue = (function IssuesListGroup__get_next_issue (all, issue) {
        if (!issue) { issue = this.current_issue; }
        var issues = all ? this.issues : this.filtered_issues;
        if (!issue) {
            if (!issues.length) { return null; }
            return issues[0]; // special case, we return the first issue if we didn't have a current one
        }
        var pos = issues.indexOf(issue);
        if (pos == issues.length - 1) { return null; }
        return issues[pos + 1];
    }); // IssuesListGroup__get_next_issue

    IssuesListGroup.prototype.on_show = (function IssuesListGroup__on_show () {
        this.collapsed = false;
        this.$node.removeClass('recent')
    }); // IssuesListGroup__on_show

    IssuesListGroup.prototype.on_hide = (function IssuesListGroup__on_hide () {
        this.collapsed = true;
    }); // IssuesListGroup__on_hide

    IssuesListGroup.prototype.get_issue_by_ident = (function IssuesListGroup__get_issue_by_ident(issue_ident) {
        var issue = null;
        for (var i = 0; i < this.issues.length; i++) {
            if (this.issues[i].number == issue_ident.number
             && this.issues[i].repository == issue_ident.repository) {
                issue = this.issues[i];
                break;
            }
        }
        return issue;
    }); // IssuesListGroup__get_issue_by_ident

    IssuesListGroup.prototype.get_issue_by_id = (function IssuesListGroup__get_issue_by_id(issue_id) {
        var issue = null;
        for (var i = 0; i < this.issues.length; i++) {
            if (this.issues[i].id == issue_id) {
                issue = this.issues[i];
                break;
            }
        }
        return issue;
    }); // IssuesListGroup__get_issue_by_id

    IssuesListGroup.prototype.update_issues_list = (function IssuesListGroup__update_issues_list (dont_reorder) {
        this.issues = $.map(this.$node.find(IssuesListIssue.selector),
                          function(node) { return node.IssuesListIssue });

        this.ask_for_filtered_issues_update();
        if (!dont_reorder) {
            this.ask_for_reorder();
        }
    }); // IssuesListGroup__update_issues_list

    IssuesListGroup.prototype.ask_for_filtered_issues_update = (function IssuesListGroup__ask_for_filtered_issues_update () {
        this.update_filtered_issues_counter += 1;
        var counter = this.update_filtered_issues_counter;
        setTimeout(function() {
            if (counter != this.update_filtered_issues_counter) {
                // during the way another update was asked
                return;
            }
            this.update_filtered_issues();
        }.bind(this), 100)

    }); // IssuesListGroup__ask_for_filtered_issues_update

    IssuesListGroup.prototype.update_filtered_issues = (function IssuesListGroup__update_filtered_issues () {
        this.filtered_issues = [];
        for (var i = 0; i < this.issues.length; i++) {
            var issue = this.issues[i];
            if (!issue.$node.hasClass('hidden')) {
                this.filtered_issues.push(issue);
            }
        }
        this.no_visible_issues = this.filtered_issues.length === 0;
        var filtered_length = this.filtered_issues.length,
            total_length = this.issues.length;
        this.$count_node.text(filtered_length == total_length ? total_length : filtered_length + '/' + total_length);
        if (this.list) {
            this.list.ask_for_selected_count_update();
        }
    }); // IssuesListGroup__update_filtered_issues

    IssuesListGroup.prototype.add_issue = (function IssuesListGroup__add_issue (issue, prepend_node) {
        if (prepend_node) {
            this.$issues_node.prepend(issue.$node);
        }
        issue.group = this;
        this.issues.unshift(issue);
        this.list.ask_for_quicksearch_results_reinit();
        this.ask_for_filtered_issues_update();
        this.ask_for_reorder();
        issue.toggle_selectable();
        this.list.ask_for_selected_count_update();
    }); // IssuesListGroup__add_issue

    IssuesListGroup.prototype.remove_issue = (function IssuesListGroup__remove_issue (issue) {
        var index = this.issues.indexOf(issue);
        if (index > -1) {
            this.issues.splice(index, 1);
        }
        issue.group = null;
        issue.$node.remove();
        if (!this.issues.length) {
            this.list.remove_group(this);
        } else {
            this.current_issue = null;
            this.ask_for_filtered_issues_update();
            this.list.ask_for_selected_count_update();
        }
    }); // IssuesListGroup__remove_issue

    IssuesListGroup.prototype.clean = (function IssuesListGroup__clean () {
        this.node.IssuesListGroup = null;
        this.$node.remove();
        this.$node = null;
        this.node = null;
        this.list = null;
        for (var i = 0; i < this.issues.length; i++) {
            this.issues[i].clean();
        }
        this.issues = [];
    }); // IssuesListGroup__clean

    IssuesListGroup.prototype.reorder_compare =  (function IssuesListGroup__reorder_compare (issue1, issue2) {
        var factor = this.list.sort_direction == 'asc' ? 1 : -1;
        if (issue1.cached_sort_value < issue2.cached_sort_value) {
            return factor * -1;
        }
        if (issue1.cached_sort_value > issue2.cached_sort_value) {
            return factor;
        }
        return issue1.position - issue2.position;
    }); // IssuesListGroup__reorder_compare

    IssuesListGroup.prototype.ask_for_reorder = (function IssuesListGroup__ask_for_reorder () {
        // idea from `_rearrange` in jquery-ui sortable
        this.reorder_counter += 1;
        var counter = this.reorder_counter;
        setTimeout(function() {
            if (counter != this.reorder_counter) {
                // during the way another reorder was asked
                return;
            }
            this.reorder();
        }.bind(this), 100)
    }); // IssuesListGroup__reorder

    IssuesListGroup.prototype.reorder = (function IssuesListGroup__reorder () {
        var i, issue, list, move, node, dest;

        for (i = 0; i < this.issues.length; i++) {
            issue = this.issues[i];
            issue.position = i;
            issue.cached_sort_value = issue.get_sort_value();
        }

        this.issues.sort(this.reorder_compare.bind(this));

        var moves = [];
        for (i = 0; i < this.issues.length; i++) {
            issue = this.issues[i];
            if (issue.position != i) {
                moves.push({issue: issue, from: issue.position, to: i});
            }
        }

        if (!moves.length) { return; }

        moves.sort(function(a, b) { return a.from - b.from });

        list = this.$issues_node[0];
        for (i = 0; i < moves.length; i++) {
            move = moves[i];
            node = move.issue.$node[0];
            dest = list.children[move.to];
            move.issue.position = move.to;
            if (node == dest) {
                continue;
            }
            if (move.to > move.from) {
                dest = dest.nextSibling; // emulate insertAfter
            }
            list.insertBefore(node, dest);
        }

        this.list.ask_for_quicksearch_results_reinit();
        this.ask_for_filtered_issues_update();
    }); // IssuesListGroup__reorder

    IssuesListGroup.prototype.toggle_multiselect = (function IssuesListGroup__toggle_multiselect(activated) {
        for (var i = 0; i < this.issues.length; i++) {
            this.issues[i].toggle_selectable(activated);
        }
    }); // IssuesListGroup__toggle_multiselect


    var IssuesList = (function IssuesList__constructor (node) {
        this.reinit_quicksearch_results_counter = 0;
        this.update_selected_count_counter = 0;
        this.set_node($(node));
    }); // IssuesList__constructor
    IssuesList.IssuesListIssue = IssuesListIssue;
    IssuesList.IssuesListGroup = IssuesListGroup;

    IssuesList.selector = '.issues-list';
    IssuesList.container_selector = '.issues-list-container';
    IssuesList.all = [];
    IssuesList.current = null;
    IssuesList.updating_ids = {};
    IssuesList.subscribed_repositories = {};

    IssuesList.prototype.unset_current = (function IssuesList__unset_current () {
        IssuesList.current = null;
    }); // IssuesList__unset_current

    IssuesList.prototype.set_current = (function IssuesList__set_current () {
        if (IssuesList.current) {
            IssuesList.current.unset_current();
        }
        IssuesList.current = this;
    }); // IssuesList__set_current

    IssuesList.init_all = (function IssuesList_init_all () {
        var $lists = $(IssuesList.selector);
        IssuesList.all = $.map($lists, function(node) { return new IssuesList(node); });
        if (!IssuesList.all.length) { return; }
        IssuesList.all[0].set_current();
        IssuesListIssue.init_events();
        IssuesListGroup.init_events();
        IssuesList.init_events();
        IssuesList.subscribe_updates();

        IssuesList.update_time_ago($lists);
        setInterval(function() {
            IssuesList.update_time_ago($lists);
        }, 60000);

    }); // IssuesList_init_all

    IssuesList.get_for_node = (function IssuesList_get_for_node($node) {
        var index = IssuesList.get_index_for_node($node);
        if (index || index === 0) {
            return IssuesList.all[index];
        }
        return null;
    }); // IssuesList_get_for_node

    IssuesList.get_index_for_node = (function IssuesList_get_index_for_node ($node) {
        for (var i = 0; i < IssuesList.all.length; i++) {
            if (IssuesList.all[i].$node[0] == $node[0] || IssuesList.all[i].$container_node[0] == $node[0]) {
                return i;
            }
        }
        return null;
    }); // IssuesList_get_index_for_node

    IssuesList.prototype.set_node = (function IssuesList__set_node ($node) {
        this.node = $node[0];
        this.node.IssuesList = this;
        this.$node = $node;
        this.$container_node = this.$node.closest(IssuesList.container_selector);
        this.$container_node[0].IssuesList = this;
        this.$empty_node = this.$node.children('.no-issues');
        this.$search_input = this.$container_node.find('.issues-quicksearch .quicksearch');
        if (!this.$search_input.length && this.$node.data('quicksearch')) {
            this.$search_input = $(this.$node.data('quicksearch'));
        }

        this.url = this.$node.data('url');
        this.base_url = this.$node.data('base-url');
        this.group_by_key = this.$node.data('group_by-key');
        this.sort_field = this.$node.data('sort-field');
        this.sort_direction = this.$node.data('sort-direction');
        this.filtered_project_number = parseInt(this.$node.data('filtered-project'), 10);

        var list = this;
        this.groups = $.map(this.$node.find(IssuesListGroup.selector),
                        function(node) { return new IssuesListGroup(node, list); });
        this.current_group = null;

        FilterManager.convert_links(this);
    }); // IssuesList__set_node

    IssuesList.add_list = (function IssuesList_add_list (list) {
        IssuesList.all.push(list);
        PanelsSwapper.update_panels_order();
        list.$container_node.trigger('reloaded');
    }); // IssuesList_add_list

    IssuesList.remove_list = (function IssuesList_remove_list (list) {
        var is_current = IssuesList.current == list,
            index = IssuesList.all.indexOf(list);
        if (is_current) {
            if (PanelsSwapper.go_prev_panel() === false) {
                PanelsSwapper.go_next_panel();
            }
        }
        if (index > -1) {
            IssuesList.all.splice(index, 1);
        }
        PanelsSwapper.update_panels_order();
    }); // IssuesList_remove_list

    IssuesList.prototype.create_empty_node = (function IssuesList__create_empty_node () {
        if (this.$empty_node.length) { return; }
        this.$empty_node = $('<div class="alert alert-info no-issues">No issues to display.</div>');
        this.$node.prepend(this.$empty_node);
    }); // IssuesList__create_empty_node

    IssuesList.prototype.replace_by_node = (function IssuesList__replace_by_node ($node) {
        var is_current = IssuesList.current == this,
            previous_groups = this.groups;
        this.node.IssuesList = null;
        this.set_node($node);
        if (is_current) {
            this.set_current();
        }
        GithubNotifications.init_item_forms();
        IssuesList.update_time_ago($node);
        activate_quicksearches(this.$search_input);
        this.init_quicksearch_events();
        PanelsSwapper.update_panel(this, this.$node.parent());

        this.$container_node.trigger('reloaded');

        for (var i = 0; i < previous_groups.length; i++) {
            previous_groups[i].clean();
        }
    }); // IssuesList__replace_by_node

    IssuesList.get_loaded_lists = (function IssuesList_get_loaded_lists () {
        return $.grep(IssuesList.all, function(list) { return !list.$node.hasClass('not-loaded'); });
    }); // IssuesList_get_loaded_lists


    IssuesList.update_time_ago = (function IssuesList_update_time_ago ($lists) {
        $lists = $lists || $(IssuesList.selector);
        for (var i = 0; i < $lists.length; i++) {
            time_ago.replace($lists[i]);
        }
    }); // IssuesList_update_time_ago

    IssuesList.on_current_list_key_event = (function IssuesList_on_current_list_key_event (list_method, current_panel, ignore_if_dropdown) {
        var decorator = function(ev) {
            if (ignore_if_dropdown && $(ev.target).closest('.dropdown-menu').length) { return; }
            if (!IssuesList.current) { return; }
            if (current_panel && (!PanelsSwapper.current_panel || PanelsSwapper.current_panel.obj != IssuesList.current)) { return; }
            return IssuesList.current[list_method]();
        };
        return Ev.key_decorate(decorator);
    }); // IssuesList_on_current_list_key_event

    IssuesList.prototype.init_quicksearch_events = (function IssuesList__init_quicksearch_events () {
        if (this.$search_input.length && !this.$search_input.data('events-done')) {
            this.$search_input.data('events-done', true);
            this.$search_input.on('quicksearch.after', $.proxy(this.on_filter_done, this));
            this.$search_input.on('keydown', jwerty.event('↓/↩', this.go_to_first_group, this));
        }
    }); // IssuesList__init_quicksearch_events

    IssuesList.init_events = (function IssuesList_init_event () {

        // keyboard events on multi-select info
        $document.on('ifChecked ifUnchecked ifToggled', IssuesList.container_selector + ' .multiselect-info input[name=select-all]', IssuesList.on_issues_selector_toggled);
        $document.on('focus', '.multiselect-info .ms-action > .dropdown-toggle', IssuesList.on_ms_action_focus);
        $document.on('click', '.multiselect-info .ms-action button.ms-action-reset', IssuesList.on_ms_action_reset);
        $document.on('click', '.multiselect-info .ms-action button.ms-action-apply:not(.disabled)', IssuesList.on_ms_action_apply);
        $document.on('ifToggled', '.multiselect-info .ms-action input[type=checkbox][indeterminate]', IssuesList.on_ms_action_checkbox_indeterminate_selector_toggled);
        $document.on('ifToggled', '.multiselect-info .ms-action input[type=radio]', IssuesList.on_ms_action_radio_selector_toggled);
        $document.on('click', '.multiselect-info .ms-action-choice a', IssuesList.on_ms_action_choice_click);
        jwerty.key('↩/space/x', IssuesList.on_ms_action_choice_keyboard_activate);
        jwerty.key('f', IssuesList.on_ms_action_focus_search_input);

        // keyboard events on list
        jwerty.key('p/k/↑', IssuesList.on_current_list_key_event('go_to_previous_item', null, true));
        jwerty.key('n/j/↓', IssuesList.on_current_list_key_event('go_to_next_item', null, true));
        jwerty.key('⇞', IssuesList.on_current_list_key_event('go_to_first_group', null, true));
        jwerty.key('⇟', IssuesList.on_current_list_key_event('go_to_last_group', null, true));
        jwerty.key('f', IssuesList.on_current_list_key_event('focus_search_input', null, true));
        jwerty.key('m', IssuesList.on_current_list_key_event('toggle_multiselect', null, true));
        jwerty.key('ctrl+u', IssuesList.on_current_list_key_event('clear_search_input', null, true));
        jwerty.key('d', IssuesList.on_current_list_key_event('toggle_details', null, true));
        jwerty.key('r', IssuesList.on_current_list_key_event('refresh', true, true));
        jwerty.key('ctrl+a', IssuesList.on_current_list_key_event('select_all_issues', null, true));
        jwerty.key('shift+ctrl+a', IssuesList.on_current_list_key_event('unselect_all_issues', null, true));
        for (var i = 0; i < IssuesList.all.length; i++) {
            IssuesList.all[i].init_quicksearch_events();
        }

        // events from options
        $document.on('click', '.issues-list-options:not(#issues-list-options-board-main) .toggle-issues-details', Ev.stop_event_decorate_dropdown(IssuesList.on_current_list_key_event('toggle_details')));
        $document.on('click', '.issues-list-options:not(#issues-list-options-board-main) .toggle-multi-select', Ev.stop_event_decorate_dropdown(IssuesList.on_current_list_key_event('toggle_multiselect')));
        $document.on('click', '.issues-list-options:not(#issues-list-options-board-main) .refresh-list', Ev.stop_event_decorate_dropdown(IssuesList.on_current_list_key_event('refresh')));
        $document.on('click', '.issues-list-options:not(#issues-list-options-board-main) .close-all-groups', Ev.stop_event_decorate_dropdown(IssuesList.on_current_list_key_event('close_all_groups')));
        $document.on('click', '.issues-list-options:not(#issues-list-options-board-main) .open-all-groups', Ev.stop_event_decorate_dropdown(IssuesList.on_current_list_key_event('open_all_groups')));

        if (window.ChartManager) {
            $document.on('click', 'a.milestone-graph-link', window.ChartManager.open_from_link);
        }
    }); // IssuesList_init_event

    IssuesList.subscribe_updates = (function IssuesList_subscribe_updates  () {
        var repositories = [];
        if (main_repository_id) {
            repositories.push(main_repository_id);
        } else if (!GithubNotifications.on_page) {
            // don't watch full repositories on notifications page, publish will be done on the
            // user's notification chanel
            for (var i = 0; i < IssuesList.all.length; i++) {
                var issues_list = IssuesList.all[i];
                repositories = repositories.concat(issues_list.$node.find(IssuesListIssue.selector).map(function() {
                    return $(this).data('repository-id');
                }).toArray());
            }
        }
        for (var j = 0; j < repositories.length; j++) {
            var repository_id = repositories[j];
            if (typeof IssuesList.subscribed_repositories[repository_id] !== 'undefined') {
                continue;
            }
            IssuesList.subscribed_repositories[repository_id] = true;
            WS.subscribe(
                'gim.front.Repository.' + repository_id + '.model.updated.is.Issue.',
                'IssuesList__on_update_alert',
                IssuesList.on_update_alert,
                'prefix'
            );
            WS.subscribe(
                'gim.front.Repository.' + repository_id + '.model.updated.is.Card',
                'IssueList__on_update_card_alert',
                IssuesList.on_update_card_alert,
                'prefix'
            );
            WS.subscribe(
                'gim.front.Repository.' + repository_id + '.model.deleted.is.Card',
                'IssueList__on_delete_card_alert',
                IssuesList.on_delete_card_alert,
                'prefix'
            );
        }
    }); // IssuesList_subscribe_updates

    IssuesList.can_update_on_alert = (function IssuesList_can_update_on_alert (issue_kwargs, method, topic, args, kwargs) {
        var js_id = issue_kwargs.js_id || issue_kwargs.id;
        if (typeof IssuesList.updating_ids[js_id] != 'undefined' || issue_kwargs.front_uuid && UUID.exists(issue_kwargs.front_uuid) && UUID.has_state(issue_kwargs.front_uuid, 'waiting')) {
            setTimeout(function() {
                IssuesList[method](topic, args, kwargs);
            }, 100);
            return false;
        }
        IssuesList.updating_ids[js_id] = true;
        return true;
    }); // IssuesList_can_update_on_alert

    IssuesList.on_update_card_alert = (function IssuesList_on_update_card_alert (topic, args, kwargs) {
        if (IssuesList.on_before_update_card_alert && IssuesList.on_before_update_card_alert(topic, args, kwargs)) {
            return;
        }
        if (!kwargs.model || kwargs.model != 'Card' || !kwargs.id || !kwargs.issue) { return; }  // we'll manage notes later
        kwargs.issue.model = 'Issue';
        kwargs.issue.front_uuid = kwargs.front_uuid;

        if (!IssuesList.can_update_on_alert(kwargs.issue, 'on_update_card_alert', topic, args, kwargs)) {
            return;
        }

        var loaded_lists = IssuesList.get_loaded_lists(),
            found_issues = 0,
            managed_issues = 0;

        for (var i = 0; i < loaded_lists.length; i++) {
            var list = loaded_lists[i],
                issue = list.get_issue_by_id(kwargs.issue.id);
            if (issue) {
                found_issues += 1;
                // we have the issue for this card, we update it
                if (issue.on_update_card_alert(topic, args, kwargs)) {
                    managed_issues += 1;
                }
            }
        }

        delete IssuesList.updating_ids[kwargs.issue.id];

        if (!found_issues || managed_issues != found_issues) {
            IssuesList.on_update_alert(topic, args, kwargs.issue)
        }

    }); // IssuesList_on_update_card_alert

    IssuesList.on_delete_card_alert = (function IssuesList_on_delete_card_alert (topic, args, kwargs) {
        if (IssuesList.on_before_delete_card_alert && IssuesList.on_before_delete_card_alert(topic, args, kwargs)) {
            return;
        }

        var loaded_lists = IssuesList.get_loaded_lists();

        if (kwargs.project_number) {
            for (var i = 0; i < loaded_lists.length; i++) {
                var list = loaded_lists[i],
                    issue = list.get_issue_by_id(kwargs.issue.id);
                if (issue) {
                    // we have the issue for this card, we remove the project from it (data/attrs)
                    issue.remove_from_project(kwargs.project_number)
                }
            }
        }

        // resetting the card info will allow to directly fetch the issue in each column
        kwargs.project_number = 0;
        kwargs.column_id = 0;
        kwargs.position = 0;
        IssuesList.on_update_card_alert(topic, args, kwargs);
    }); // IssuesList_on_delete_card_alert

    IssuesList.on_update_alert = (function IssuesList_on_update_alert (topic, args, kwargs) {
        if (!kwargs.model || kwargs.model != 'Issue' || !kwargs.id || !kwargs.url) { return; }

        if (!IssuesList.can_update_on_alert(kwargs, 'on_update_alert', topic, args, kwargs)) {
            return;
        }

        var loaded_lists = IssuesList.get_loaded_lists();

        var message_conf = {
            count: 0,
            expected_count: loaded_lists.length,
            done: false,
            no_extended_message: loaded_lists.length > 1,
            on_list_done: function() {
                message_conf.count ++;
                if (message_conf.count == message_conf.expected_count) {
                    var front_uuid_exists = UUID.exists(kwargs.front_uuid);
                    if (!message_conf.done && (!kwargs.front_uuid || !front_uuid_exists)) {
                        // the issue is not in a list, so we fetch it again to display the msg
                        $.get(kwargs.url).done(function (data) {
                            var $data = $(data);
                            IssuesListIssue.finalize_alert($data, kwargs, front_uuid_exists, $data, null, 'hidden', message_conf);
                        });
                    }
                }

            }
        };

        for (var i = 0; i < loaded_lists.length; i++) {
            var list = loaded_lists[i],
                issue = list.get_issue_by_id(kwargs.id);
            if (issue) {
                issue.on_update_alert(topic, args, kwargs, message_conf);
            } else {
                list.on_issue_create_alert(topic, args, kwargs, message_conf);
            }

        }
    }); // IssuesList_on_update_alert

    IssuesList.prototype.create_group = (function IssuesList__create_group (filter_value, filter_text, filter_description) {
        var $group = this.$node.find(IssuesListGroup.template_selector).clone();
        $group.removeClass('template');
        if (filter_value != null) {
            $group.attr('data-group_by-value', filter_value);
        }
        if (filter_text != null && filter_value != '' && filter_value != '__none__') {
            var $span = $group.find('span.title');
            $span.text(filter_text);
            if (filter_description) {
                $span.append('<span>- ' + filter_description + '</span>');
            }
        }
        var new_uuid = UUID.generate();
        $group.children('.box-header').attr('data-target', '#group_by-list-' + new_uuid);
        $group.children('.issues-group-issues').attr('id', 'group_by-list-' + new_uuid);
        if (this.$empty_node.length) {
            this.$empty_node.hide();
            this.$empty_node.after($group);
        } else {
            this.$node.prepend($group);
        }
        $group.show();
        var group = new IssuesListGroup($group[0], this);
        this.groups.unshift(group);
        return group;
    }); // IssuesList__create_group

    IssuesList.prototype.remove_group = (function IssuesList__remove_group (group) {
        var index = this.groups.indexOf(group);
        if (index > -1) {
            this.groups.splice(index, 1);
        }
        if (this.current_group == group) {
            group.unset_current();
            if (this.groups.length) {
                this.groups[index ? index - 1 : 1].set_current(false)
            }
        }
        group.clean();
        if (!this.groups.length) {
            this.$node.find('.alert').hide();
            this.create_empty_node();
            this.$empty_node.show();
        }

        this.ask_for_quicksearch_results_reinit();
        this.ask_for_selected_count_update();
    }); // IssuesList__remove_group

    IssuesList.prototype.get_group_for_value = (function IssuesList__get_group_for_value (value) {
        for (var i = 0; i < this.groups.length; i++) {
            if (this.groups[i].group_by_value == value) {
                return this.groups[i];
            }
        }
        return null;
    }); // IssuesList__get_group_for_value

    IssuesList.prototype.on_issue_create_alert = (function IssuesList__on_issue_create_alert (topic, args, kwargs, message_conf) {
        var list = this,
            front_uuid_exists = UUID.exists(kwargs.front_uuid);

        message_conf = message_conf || {};

        $.get(kwargs.url + '?referer=' + window.encodeURIComponent(list.url)).done(function(data) {

            // continue only if not already done
            if (list.get_issue_by_id(kwargs.id)) { return; }

            var $data = $(data),
                issue = new IssuesListIssue($data[0], null),
                filter, group,
                $containers = IssueDetail.get_containers_for_ident({'id': kwargs.id});

            if (!$containers.length) { $data.addClass('recent'); }

            if (list.group_by_key) {
                filter = issue.get_filter_for(list.group_by_key);
                group = list.get_group_for_value(filter.value) || list.create_group(filter.value, filter.text, filter.description);
            } else {
                // no group by: only one group
                group = list.groups.length ? list.groups[0] : list.create_group(null, null, null);
            }
            group.add_issue(issue, true);
            if (list.groups.length == 1) {
                group.open();
            } else if (!$containers.length) {
                group.$node.addClass('recent');
            }
            list.ask_for_quicksearch_results_reinit();

            FilterManager.convert_links(list);

            IssuesListIssue.finalize_alert(issue.$node, kwargs, front_uuid_exists, $data, $containers, 'added', message_conf);

            if (kwargs.front_uuid && kwargs.is_new && front_uuid_exists) {
                $data.removeClass('recent');
            }
        }).always(function() {
            message_conf.on_list_done();
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                UUID.set_state(kwargs.front_uuid, '');
            }
            delete IssuesList.updating_ids[kwargs.id];
        });
    }); // IssuesList__on_issue_create_alert

    IssuesList.prototype.on_filter_done = (function IssuesList__on_filter_done () {
        if (this.skip_on_filter_done_once) {
            this.skip_on_filter_done_once = false;
            return;
        }
        var continue_issue_search = this.$search_input.val() !== '';
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            group.update_filtered_issues();
            if (continue_issue_search !== false) {
                continue_issue_search = group.go_to_first_issue(true);
                if (continue_issue_search === false) {
                    this.$search_input.focus();
                }
            }
        }
        if (continue_issue_search !== false) {
            this.go_to_first_group();
            this.$search_input.focus();
        }
        this.ask_for_selected_count_update();
    }); // on_filter_done

    IssuesList.prototype.focus_search_input = (function IssuesList__focus_search_input () {
        if (!this.$search_input.length) { return; }
        this.$search_input.focus();
        return false;
    }); // IssuesList__focus_search_input

    IssuesList.prototype.clear_search_input = (function IssuesList__clear_search_input () {
        if (!this.$search_input.length) { return; }
        this.$search_input.val('');
        this.$search_input.trigger('quicksearch.refresh');
        return false;
    }); // IssuesList__clear_search_input

    IssuesList.prototype.go_to_previous_item = (function IssuesList__go_to_previous_item () {
        // if we have no current group, abort
        if (!this.current_group) { return; }
        // try to select the previous issue on the current group
        if (this.current_group.go_to_previous_item() === false) {
            return false; // stop event propagation
        }
        // no previous issue on the current group, try to select the previous group
        var previous_group = this.get_previous_group();
        if (!previous_group) {
            if (this.$search_input.length) {
                this.current_group.unset_current();
                this.$search_input.focus();
            }
            return false; // stop event propagation
        }
        if (previous_group.collapsed || previous_group.no_visible_issues) {
            previous_group.set_current(true);
        } else {
            previous_group.set_current();
            previous_group.go_to_last_issue();
        }
        return false; // stop event propagation
    }); // IssuesList__go_to_previous_item

    IssuesList.prototype.go_to_next_item = (function IssuesList__go_to_next_item () {
        // if we have no current group, select the first group if we have one
        if (!this.current_group) {
            if (!this.groups.length) { return; }
            this.groups[0].set_current(true);
            return false; // stop event propagation
        }
        // try to select the next issue on the current group
        if (this.current_group.go_to_next_item() === false) {
            return false; // stop event propagation
        }
        // no next issue on the current group, try to select the next group
        var next_group = this.get_next_group();
        if (!next_group) { return; }
        this.current_group.unset_current();
        next_group.set_current(true);
        return false; // stop event propagation
    }); // IssuesList__go_to_next_item

    IssuesList.prototype.go_to_first_issue = (function IssuesList__go_to_first_issue () {
        // select the first non empty group
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            if (!group.no_visible_issues) {
                group.set_current(true);
                break;
            }
        }
        if (!this.current_group) { return; }
        this.current_group.open();
        this.current_group.go_to_first_issue();
    }); // IssuesList__go_to_first_issue

    IssuesList.prototype.get_previous_group = (function IssuesList__get_previous_group () {
        if (!this.current_group) { return null; }
        var pos = this.groups.indexOf(this.current_group);
        if (pos < 1) { return null; }
        return this.groups[pos - 1];
    }); // IssuesList__get_previous_group

    IssuesList.prototype.get_next_group = (function IssuesList__get_next_group () {
        if (!this.current_group) {
            if (!this.groups.length) { return null; }
            return this.groups[0];
        }
        var pos = this.groups.indexOf(this.current_group);
        if (pos == this.groups.length - 1) { return null; }
        return this.groups[pos + 1];
    }); // IssuesList__get_next_group

    IssuesList.prototype.go_to_first_group = (function IssuesList__go_to_first_group () {
        if (!this.groups.length) { return; }
        this.groups[0].set_current(true);
        return false; // stop event propagation
    }); // IssuesList__go_to_first_group

    IssuesList.prototype.go_to_last_group = (function IssuesList__go_to_last_group () {
        if (!this.groups.length) { return; }
        this.groups[this.groups.length - 1].set_current(true);
        return false; // stop event propagation
    }); // IssuesList__go_to_last_group

    IssuesList.toggle_details = (function IssuesList_toggle_details () {
        for (var i = 0; i < IssuesList.all.length; i++) {
            var list = IssuesList.all[i];
            list.toggle_details();
        }
        return false; // stop event propagation
    }); // IssuesList_toggle_details

    IssuesList.prototype.toggle_details = (function IssuesList__toggle_details () {
        this.$node.toggleClass('without-details');
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            if (!group.collapsed) {
                group.$issues_node.height('auto');
            }
        }
        return false; // stop event propagation
    }); // IssuesList__toggle_details

    IssuesList.refresh = (function IssuesList_refresh () {
        var loaded_lists = IssuesList.get_loaded_lists();
        for (var i = 0; i < loaded_lists.length; i++) {
            var list = loaded_lists[i];
            list.refresh();
        }
        return false; // stop event propagation
    }); // IssuesList_refresh

    IssuesList.prototype.refresh = (function IssuesList__refresh () {
        IssuesFilters.reload_filters_and_list(
            this.url,
            this.$container_node.prev(IssuesFilters.selector),
            this.$container_node,
            true
        );
        return false; // stop event propagation
    }); // IssuesList__refresh

    IssuesList.close_all_groups = (function IssuesList_close_all_groups () {
        var loaded_lists = IssuesList.get_loaded_lists();
        for (var i = 0; i < loaded_lists.length; i++) {
            var list = loaded_lists[i];
            list.close_all_groups();
        }
        return false; // stop event propagation
    }); // IssuesList_close_all_groups

    IssuesList.prototype.close_all_groups = (function IssuesList__close_all_groups () {
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            group.close();
        }
        return false; // stop event propagation
    }); // IssuesList__close_all_groups

    IssuesList.open_all_groups = (function IssuesList_open_all_groups () {
        var loaded_lists = IssuesList.get_loaded_lists();
        for (var i = 0; i < loaded_lists.length; i++) {
            var list = loaded_lists[i];
            list.open_all_groups();
        }
        return false; // stop event propagation
    }); // IssuesList_open_all_groups

    IssuesList.prototype.open_all_groups = (function IssuesList__open_all_groups () {
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            group.open();
        }
        return false; // stop event propagation
    }); // IssuesList__open_all_groups

    IssuesList.get_issue_by_ident = (function IssuesList_get_issue_by_ident(issue_ident) {
        var issue = null;
        for (var i = 0; i < IssuesList.all.length; i++) {
            issue = IssuesList.all[i].get_issue_by_ident(issue_ident);
            if (issue) { break; }
        }
        return issue;
    }); // IssuesList_get_issue_by_ident

    IssuesList.get_issues_by_ident = (function IssuesList_get_issues_by_ident(issue_ident) {
        var issues = [], issue;
        for (var i = 0; i < IssuesList.all.length; i++) {
            issue = IssuesList.all[i].get_issue_by_ident(issue_ident);
            if (issue) {
                issues.push(issue);
            }
        }
        return issues;
    }); // IssuesList_get_issues_by_ident

    IssuesList.prototype.get_issue_by_ident = (function IssuesList__get_issue_by_ident(issue_ident) {
        var issue = null;
        for (var i = 0; i < this.groups.length; i++) {
            issue = this.groups[i].get_issue_by_ident(issue_ident);
            if (issue) { break; }
        }
        return issue;
    }); // IssuesList__get_issue_by_ident

    IssuesList.get_issue_by_id = (function IssuesList_get_issue_by_id(issue_id) {
        var issue = null;
        for (var i = 0; i < IssuesList.all.length; i++) {
            issue = IssuesList.all[i].get_issue_by_id(issue_id);
            if (issue) { break; }
        }
        return issue;
    }); // IssuesList_get_issue_by_id

    IssuesList.get_issues_by_id = (function IssuesList_get_issues_by_id(issue_id) {
        var issues = [], issue;
        for (var i = 0; i < IssuesList.all.length; i++) {
            issue = IssuesList.all[i].get_issue_by_id(issue_id);
            if (issue) {
                issues.push(issue);
            }
        }
        return issues;
    }); // IssuesList_get_issues_by_id

    IssuesList.prototype.get_issue_by_id = (function IssuesList__get_issue_by_id(issue_id) {
        var issue = null;
        for (var i = 0; i < this.groups.length; i++) {
            issue = this.groups[i].get_issue_by_id(issue_id);
            if (issue) { break; }
        }
        return issue;
    }); // IssuesList__get_issue_by_id

    IssuesList.prototype.ask_for_quicksearch_results_reinit = (function IssuesList__ask_for_quicksearch_results_reinit () {
        this.reinit_quicksearch_results_counter += 1;
        var counter = this.reinit_quicksearch_results_counter;
        setTimeout(function() {
            if (counter != this.reinit_quicksearch_results_counter) {
                // during the way another reinit was asked
                return;
            }
            this.reinit_quicksearch_results();
        }.bind(this), 100)
    }); // IssuesList__ask_for_quicksearch_results_reinit

    IssuesList.prototype.reinit_quicksearch_results = (function IssuesList__reinit_quicksearch_results () {
        this.init_quicksearch_events();
        this.$search_input.data('quicksearch').cache();
        this.ask_for_selected_count_update();
    }); // IssuesList__reinit_quicksearch_results

    IssuesList.prototype.toggle_multiselect = (function IssuesList__toggle_multiselect (activated) {
        if (typeof activated == 'undefined') {
            this.$container_node.toggleClass('multiselect-mode');
            activated = this.$container_node.hasClass('multiselect-mode');
        } else {
            activated = !!activated;
            if (activated == this.$container_node.hasClass('multiselect-mode')) {
                return;
            }
            this.$container_node.toggleClass('multiselect-mode', activated);
        }
        for (var i = 0; i < this.groups.length; i++) {
            this.groups[i].toggle_multiselect(activated);
        }
        this.last_directly_touched_selectable_issue = null;

        if (activated) {
            var $multiselect_header = this.$container_node.children('.multiselect-info');
            if (!$multiselect_header.length) {
                $multiselect_header = IssuesList.get_multiselect_info_node();
                this.$node.before($multiselect_header);
                $multiselect_header.find('input[name=select-all]').iCheck({checkboxClass: 'icheckbox_flat-blue'});
            }
        } else {
            this.$container_node.find('.multiselect-info').remove();
        }

        return false; // stop event propagation
    }); // IssuesList__toggle_multiselect

    IssuesList.get_multiselect_info_node = (function IssuesList_get_multiselect_info_node() {
        var $template = $('#main .multiselect-info.template');
        if (!$template.length) {
            $template = $(
                '<div class="multiselect-info template" style="display: none">' +
                    '<div class="ms-selector" title="Click to select/unselect all"><input type="checkbox" name="select-all"/></div>' +
                    '<span class="ms-counter">Nothing selected</span>' +
                    '<nav class="navbar navbar-no-rounded ms-actions">' +
                        '<div class="navbar-inner">' +
                            '<ul class="nav">' +
                                '<li class="dropdown ms-action ms-labels" data-action="labels">' +
                                    '<a href="#" role="button" class="dropdown-toggle" data-toggle="dropdown" title="Change labels"><span><i class="fa fa-tags"></i><span class="ms-action-name">Labels</span><b class="caret"></b></span></a>' +
                                    '<div class="dropdown-menu" role="menu"><ul><li class="disabled"><a href="#"><i class="fa fa-spinner fa-spin"> </i> Loading</a></li></ul></div>' +
                                '</li>' +
                                '<li class="divider-vertical"></li>' +
                                '<li class="dropdown ms-action ms-milestone" data-action="milestone">' +
                                    '<a href="#" role="button" class="dropdown-toggle" data-toggle="dropdown" title="Change milestone"><span><i class="fa fa-tasks"></i><span class="ms-action-name">Milestone</span><b class="caret"></b></span></a>' +
                                    '<div class="dropdown-menu" role="menu"><ul><li class="disabled"><a href="#"><i class="fa fa-spinner fa-spin"> </i> Loading</a></li></ul></div>' +
                                '</li>' +
                                '<li class="divider-vertical"></li>' +
                                '<li class="dropdown ms-action ms-assignees" data-action="assignees">' +
                                    '<a href="#" role="button" class="dropdown-toggle" data-toggle="dropdown" title="Change assignees"><span><i class="fa fa-hand-o-right"></i><span class="ms-action-name">Assignees</span><b class="caret"></b></span></a>' +
                                    '<div class="dropdown-menu" role="menu"><ul><li class="disabled"><a href="#"><i class="fa fa-spinner fa-spin"> </i> Loading</a></li></ul></div>' +
                                '</li>' +
                                '<li class="divider-vertical"></li>' +
                                '<li class="dropdown ms-action ms-projects" data-action="projects">' +
                                    '<a href="#" role="button" class="dropdown-toggle" data-toggle="dropdown" title="Change projects"><span><i class="fa fa-align-left fa-rotate-90"></i><span class="ms-action-name">Projects</span><b class="caret"></b></span></a>' +
                                    '<div class="dropdown-menu pull-right" role="menu"><ul><li class="disabled"><a href="#"><i class="fa fa-spinner fa-spin"> </i> Loading</a></li></ul></div>' +
                                '</li>' +
                                '<li class="divider-vertical"></li>' +
                                '<li class="dropdown ms-action ms-state" data-action="state">' +
                                    '<a href="#" role="button" class="dropdown-toggle" data-toggle="dropdown" title="Change state"><span><i class="fa fa-dot-circle-o"></i><span class="ms-action-name">State</span><b class="caret"></b></span></a>' +
                                    '<div class="dropdown-menu pull-right" role="menu"><ul><li class="disabled"><a href="#"><i class="fa fa-spinner fa-spin"> </i> Loading</a></li></ul></div>' +
                                '</li>' +
                            '</ul>' +
                        '</div>' +
                    '</nav>' +
                '</div>'
            );
            $('#main').append($template);
        }

        var $result = $template.clone();
        $result.attr('style', '').removeClass('template');
        if ($body.data('repository-has-projects')) {
            $result.addClass('with-projects');
        } else {
            var $projects_dropdown = $result.find('.ms-projects');
            $projects_dropdown.prev('.divider-vertical').remove();
            $projects_dropdown.remove();
            $result.find('.ms-assignees .dropdown-menu').addClass('pull-right');
        }
        return $result;

    }); // IssuesList_get_multiselect_info_node

    IssuesList.toggle_multiselect = (function IssuesList_toggle_multiselect(activated) {
        for (var i = 0; i < IssuesList.all.length; i++) {
            var list = IssuesList.all[i];
            list.toggle_multiselect(activated);
        }
        return false; // stop event propagation
    }); // IssuesList_toggle_multiselect

    IssuesList.prototype.ask_for_selected_count_update = (function IssuesList__ask_for_selected_count_update () {
        // idea from `_rearrange` in jquery-ui sortable
        // if (!this.$container_node.hasClass('multiselect-mode')) { return; }  # may be called to often, let the check be done in `update_selected_count`
        this.update_selected_count_counter += 1;
        var counter = this.update_selected_count_counter;
        setTimeout(function() {
            if (counter != this.update_selected_count_counter) {
                // during the way another update was asked
                return;
            }
            this.update_selected_count();
        }.bind(this), 100)
    }); // IssuesList__ask_for_selected_count_update

    IssuesList.get_selected_count_to_display = (function IssuesList_get_selected_count_to_display (count, count_hidden, total_count) {
        var result = 'Nothing selected';
        if (count > 1) {
            result = count;
            if (count_hidden > 0) {
                result += '&nbsp;selected<br /><span>';
                if (count_hidden == count) {
                    result += ' (filtered&nbsp;out)';
                } else {
                    result += ' (' + count_hidden + '&nbsp;filtered&nbsp;out)';
                }
                result += '</span>';
            } else {
                result += ' selected';
            }
        } else if (count > 0) {
            if (count_hidden > 0) {
            result = '1&nbsp;selected, filtered&nbsp;out';

            } else {
                result = '1 selected';
            }
        }
        return result;
    }); // IssuesList_get_selected_count_to_display

    IssuesList.set_select_all_input_state = (function IssuesList_set_select_all_input_state ($input, count, count_hidden, total_count) {
        var checked = $input.prop('checked');
        if (count && count == total_count) {
            $input.iCheck('determinate');
            if (!checked) {
                $input.iCheck('check');
            }
        } else if (count <= 0) {
            $input.iCheck('determinate');
            if (checked) {
                $input.iCheck('uncheck');
            }
        } else {
            $input.iCheck('indeterminate');
        }

        $input.closest('.multiselect-info').find('.ms-action').data('selection-changed', true);

        $input.data('selected-count', {
            count: count,
            count_hidden: count_hidden,
            total_count: total_count
        });
    }); // IssuesList_set_select_all_input_state

    IssuesList.prototype.update_selected_count = (function IssuesList__update_selected_count () {
        if (!this.$container_node.hasClass('multiselect-mode')) { return; }
        var count = 0, count_hidden = 0, total_count = 0;

        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            for (var j = 0; j < group.issues.length; j++) {
                var issue = group.issues[j];
                if (!issue.is_real_issue()) { continue; }
                total_count += 1;
                if (issue.is_selected()) {
                    count += 1;
                    count_hidden += 1;
                }
            }
            for (var k = 0; k < group.filtered_issues.length; k++) {
                var issue = group.filtered_issues[k];
                if (!issue.is_real_issue()) { continue; }
                if (issue.is_selected()) {
                    count_hidden -= 1;
                }
            }
        }

        this.$container_node.find('.multiselect-info .ms-counter').html(IssuesList.get_selected_count_to_display(count, count_hidden, total_count));
        var $input = this.$container_node.find('.multiselect-info input[name=select-all]');
        IssuesList.set_select_all_input_state($input, count, count_hidden, total_count);
    }); // IssuesList__update_selected_count

    IssuesList.prototype.get_issues_between = (function IssuesList__get_issues_between (issue1, issue2) {
        if (issue1 && !issue2) {
            return [issue1];
        }
        if (issue2 && !issue1) {
            return [issue2];
        }
        var started = false, finished = false, end = null, issues = [];
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            for (var j = 0; j < group.filtered_issues.length; j++) {
                var issue = group.filtered_issues[j];
                if (!issue.is_real_issue()) { continue; }
                if (started) {
                    issues.push(issue);
                    if (issue == end) {
                        finished = true;
                        break;
                    }
                } else {
                    if (issue == issue1) {
                        end = issue2;
                    } else if (issue == issue2) {
                        end = issue1;
                    }
                    if (end) {
                        started = true;
                        issues.push(issue);
                    }
                }
            }
            if (finished) {
                break;
            }
        }

        if (!(started && finished)) {
            // both entries where not in filtered issues
            return [issue2];
        }

        return issues;
    }); // IssuesList__get_issues_between

    IssuesList.prototype.select_all_issues = (function IssuesList__select_all_issues (unselect) {
        if (!this.$container_node.hasClass('multiselect-mode')) { return; }
        for (var i = 0; i < this.groups.length; i++) {
            var group = this.groups[i];
            for (var j = 0; j < group.filtered_issues.length; j++) {
                var issue = group.filtered_issues[j];
                if (!issue.is_real_issue()) { continue; }
                issue.toggle_selected(!unselect, null);
            }
        }
        this.last_directly_touched_selectable_issue = null;
        this.ask_for_selected_count_update();
        return false;
    }); // IssuesList__select_all_issues

    IssuesList.prototype.unselect_all_issues = (function IssuesList__unselect_all_issues () {
        this.select_all_issues(true);
    }); // IssuesList__unselect_all_issues

    IssuesList.on_issues_selector_toggled = (function IssuesList_on_issues_selector_toggled () {
        var $input = $(this),
            list = $input.closest(IssuesList.container_selector)[0].IssuesList;
        if ($input.prop('checked')) {
            return list.select_all_issues();
        } else {
            return list.unselect_all_issues();
        }
    }); // IssuesList_on_issues_selector_toggled

    IssuesList.get_selected_issues_ids = (function IssuesList__get_selected_issues ($element) {
        var $holder = $element.closest('.issues-list');
        if (!$holder.length) {
            $holder = $body;
        }
        var $inputs = $holder.find('.issue-item .selector input:checked');
        var ids = [];
        for (var i = 0; i < $inputs.length; i++) {
            ids.push($inputs[i].value);
        }
        return ids;
    }); // IssuesList__get_selected_issues

    IssuesList.load_multiselect_list = (function IssuesList_load_multiselect_list ($dropdown) {
        var $selector_all = $dropdown.closest('.multiselect-info').find('.ms-selector input[name=select-all]'),
            $dropdown_menu = $dropdown.find('.dropdown-menu').first(),
            selected_count = $selector_all.data('selected-count'),
            uuid, action, url, data, context;

        if (!selected_count || !selected_count.count) {
            $dropdown_menu.empty().append('<li class="disabled"><a href="#">Nothing selected</a></li>');
            $dropdown.removeClass('loaded');
            return;
        }
        if ($dropdown.data('selection-changed')) {
            $dropdown.data('selection-changed', false);
        } else {
            if ($dropdown.data('loading')) {
                return;
            }
            if ($dropdown.data('loaded')) {
                setTimeout(function() { $dropdown.find('.quicksearch-widget input').focus(); }, 200);
                return;
            }
            uuid = $dropdown.data('loading-uuid');
        }

        $dropdown.data('loading', true);
        $dropdown.data('loaded', false);

        if (!uuid) {
            uuid = UUID.generate();
            $dropdown.data('loading-uuid', uuid);
        }

        $dropdown_menu.empty().append('<li class="disabled"><a href="#"><i class="fa fa-spinner fa-spin"> </i> Loading</a></li>');
        $dropdown.removeClass('loaded');

        action = $dropdown.data('action');
        url = $body.data('repository-multiselect-base-url') + action + '/list/';
        data = {
            issues: IssuesList.get_selected_issues_ids($dropdown),
            csrfmiddlewaretoken: $body.data('csrf')
        };

        context = {
            action: action,
            uuid: uuid,
            $dropdown: $dropdown,
            $dropdown_menu: $dropdown_menu
        };

        $.post(url, data)
            .done($.proxy(IssuesList.multiselect_list_loaded, context))
            .fail($.proxy(IssuesList.multiselect_list_failed, context));

    }); // IssuesList_load_multiselect_list

    IssuesList.multiselect_list_loaded = (function IssuesList_multiselect_list_loaded (data) {
        if (this.uuid != this.$dropdown.data('loading-uuid')) { return; }
        this.$dropdown_menu.replaceWith(data);
        this.$dropdown.data('loading', false);
        this.$dropdown.data('loaded', true);

        this.$dropdown_menu = this.$dropdown.find('.dropdown-menu').first();

        if (this.$dropdown_menu.hasClass('empty')) {
            return;
        }
        this.$dropdown.addClass('loaded');

        var $inputs = this.$dropdown_menu.find('input[type=checkbox], input[type=radio]');
        for (var i = 0; i < $inputs.length; i++) {
            var $input = $($inputs[i]);
            if ($inputs[i].type == 'checkbox') {
                $input.iCheck({checkboxClass: 'icheckbox_flat-blue'});
            } else {
                $input.iCheck({radioClass: 'iradio_flat-blue'});
            }
            if ($input.attr('indeterminate')) {
                $input.iCheck('indeterminate');
                $input.data('previously-indeterminate', true);
            }
        }

        var $quicksearch_input = this.$dropdown_menu.find('.quicksearch-widget input');
        if ($quicksearch_input.length) {
            $quicksearch_input.on('click', function(ev) { ev.stopPropagation(); });

            // $quicksearch_input.focus();
            setTimeout(function() { $quicksearch_input.focus(); }, 200);
            $quicksearch_input.on('quicksearch.after', IssuesList.on_ms_quicksearch);
        }

        // only way to bypass bootstrap taking hand over the "arrow up" key
        this.$dropdown.on('keydown', jwerty.event('↑', IssuesList.on_ms_action_go_up_from_first_item));


    }); // IssuesList_multiselect_list_loaded

    IssuesList.on_ms_quicksearch = (function IssuesList_on_ms_quicksearch () {
        var $input = $(this),
            $dropdown_menu = $input.closest('.dropdown-menu'),
            $groups = $dropdown_menu.find('[data-group]'),
            group_length = {},
            first_divider_checked = false;

        for (var i = 0; i < $groups.length; i++) {
            var $group = $($groups[i]),
                group = $group.data('group');
            if (typeof group_length[group] == 'undefined') {
                group_length[group] = $dropdown_menu.find('[data-related-to=' + group + ']:not(.hidden)').length;
            }
            var visible = !!group_length[group];
            $group.toggle(visible);
            if (visible && !first_divider_checked) {
                first_divider_checked = true;
                if ($group.hasClass('divider')) {
                    $group.hide();
                }
            }
        }
    }); // IssuesList_on_ms_quicksearch

    IssuesList.multiselect_list_failed = (function IssuesList_multiselect_list_failed (xhr, data) {
        if (this.uuid != this.$dropdown.data('loading-uuid')) { return; }
        this.$dropdown_menu.empty().append('<li class="disabled"><a href="#">Loading failed</a></li>')
        this.$dropdown.data('loading', false);
        this.$dropdown.data('loaded', false);
    }); // IssuesList_multiselect_list_failed

    IssuesList.on_ms_action_focus = (function IssuesList_on_ms_action_focus () {
        var $dropdown = $(this).closest('.dropdown');
        IssuesList.load_multiselect_list($dropdown);
    }); // IssuesList_on_ms_action_focus

    IssuesList.on_ms_action_reset = (function IssuesList_on_ms_action_reset () {
        var $dropdown = $(this).closest('.dropdown');
        $dropdown.data('loaded', false);
        IssuesList.load_multiselect_list($dropdown);
        return false;
    }); // IssuesList_on_ms_action_reset

    IssuesList.on_ms_action_apply = (function IssuesList_on_ms_action_apply () {
        var $dropdown_menu = $(this).closest('.dropdown-menu'),
            action = $dropdown_menu.closest('.dropdown').data('action'),
            issues_count = $dropdown_menu.data('issues-count'),
            types = ['u2c', 'c2u', 'i2c', 'i2u'],
            action_classes = {
                added: 'text-open',
                removed: 'text-closed'
            },
            action_rules = {
                labels: {},
                milestone: {
                    reverse: true,
                },
                assignees: {
                    added: 'assigned',
                    removed: 'unassigned'
                },
                projects: {
                    reverse: true,
                },
                state: {
                    reverse: true,
                    no_detail: true,
                    added: 'reopened',
                    removed: 'closed',
                }
            },
            rules = {
                // unchecked to checked
                'u2c': {'final': 'set', 'action': 'added', $inputs: $dropdown_menu.find('.ms-action-choice input:not([indeterminate]):not([checked]):checked'), counter: function() { return issues_count; }},
                // checked to unchecked
                'c2u': {'final': 'unset', 'action': 'removed', $inputs: $dropdown_menu.find('.ms-action-choice input:not([indeterminate])[checked]:not(:checked)'), counter: function() { return issues_count; }},
                // indeterminate to checked
                'i2c': {'final': 'set', 'action': 'added', $inputs: $dropdown_menu.find('.ms-action-choice input[indeterminate]:not(:indeterminate):checked'), counter: function(count) { return issues_count - count; }},
                // indeterminate to unchecked
                'i2u': {'final': 'unset', 'action': 'removed', $inputs: $dropdown_menu.find('.ms-action-choice input[indeterminate]:not(:indeterminate):not(:checked)'), counter: function(count) { return count; }}
            },
            $modal = IssuesList.get_multiselect_action_confirm_modal_node(),
            $modal_header = $modal.find('.modal-header h6'),
            $summary_container = $modal.find('.modal-body > ul'),
            $modal_confirm_btn = $modal.find('.btn-confirm'),
            data = {'set': [], 'unset': []},
            actions_count = 0,
            i, j, type, rule, action_rule, action_string, issues_string, $input, count, value, $summary, $info;

        for (i = 0; i < types.length; i++) {
            type = types[i];
            rule = rules[type];
            action_rule = action_rules[action];
            for (j = 0; j < rule.$inputs.length; j++) {
                actions_count += 1;
                $input = $(rule.$inputs[j]);
                value = $input.attr('value');
                if (value == "0") { continue; } // no milestone, not in project, state closed
                count = rule.counter($input.data('count') || 0);

                action_string = ' will be <strong class="' + action_classes[rule.action] + '">' + (action_rule[rule.action] || rule.action) + '</strong> ';
                if (!action_rule.no_detail) {
                    action_string += (rule.action == 'added' ? 'to' : 'from') + ' ';
                }
                issues_string = '<strong>' + count + '</strong> issue'  + (count > 1 ? 's' : '');
                $info = $input.closest('.ms-action-choice').find('.ms-action-content').clone();
                $info.find('.hidden').removeClass('hidden');

                $summary = $('<li></li>');
                if (action_rule.reverse || !action_rule.no_detail) {
                    $summary.prepend(action_rule.reverse ? issues_string : $info);
                }
                $summary.append(action_string);
                if (!action_rule.reverse || !action_rule.no_detail) {
                    $summary.append(action_rule.reverse ? $info : issues_string);
                }
                $summary_container.append($summary);

                data[rule.final].push(value);
            }
        }

        if (actions_count) {
            $summary_container.before("<p>Please verify and confirm:</p>");

            data.issues = $dropdown_menu.data('issues');
            data.hash = $dropdown_menu.data('issues-hash');
            data.csrfmiddlewaretoken = $body.data('csrf');
            data.front_uuid = UUID.generate();

            $modal_confirm_btn.on('click', {
                action: action,
                post_data: data
            }, IssuesList.on_ms_action_confirm);

        } else {
            $summary_container.before("<p style='text-align: center'>It appears that there's nothing to do!</p>");
            $summary_container.remove();
            $modal_confirm_btn.remove();
        }

        $modal_header.text('Multi-changes of ' + action);
        $body.append($modal);
        $modal.modal('show').on('hidden.modal', function() { $modal.remove() });

        return false;

    }); // IssuesList_on_ms_action_apply

    IssuesList.on_ms_action_confirm = (function IssuesList_on_ms_action_confirm (ev) {
        var $button = $(this), $modal, modal, url, context;

        if ($button.hasClass('disabled ')) { return; }

        $button.addClass('loading disabled');

        // Forbid closing the modal
        $modal = $button.closest('.modal');
        modal = $modal.data('modal');
        modal.options.keyboard = false;
        modal.$element.off('keyup');
        modal.$backdrop.off('click');
        $modal.find('.btn[data-dismiss]').hide();

        url = $body.data('repository-multiselect-base-url') + ev.data.action + '/apply/';

        context = {
            $modal: $modal,
            action: ev.data.action
        };

        $.post(url, ev.data.post_data)
            .done($.proxy(IssuesList.multiselect_confirm_done, context))
            .fail($.proxy(IssuesList.multiselect_confirm_failed, context));

        // Forbid reuse of list
        $('.ms-action.ms-' + ev.data.action + ' .ms-action-apply').addClass('disabled').attr('title', 'This list needs to be reset');
        $('.ms-action.ms-' + ev.data.action + ' input').iCheck('disable').attr('title', 'This list needs to be reset');

    });

    IssuesList.multiselect_confirm_done = (function IssuesList_multiselect_confirm_done (data) {
        var $modal_body = this.$modal.find('.modal-body'),
            $ul = $modal_body.children('ul'),
            $ul_failures;
        $modal_body.children('p').text('Recap:');
        $ul.empty();
        if (data.count_success) {
            $ul.append('<li><strong class="text-open">' + data.count_success + ' issue' + (data.count_success > 1 ? 's</strong> are' : '</strong> is') + ' currently being updated</li>');
        }
        if (data.failures.length > 0) {
            $ul.append('<li><strong class="text-closed">' + data.failures.length + ' issue' + (data.failures.length > 1 ? 's' : '') + "</strong> couldn't be updated:<ul></ul></li>");
            $ul_failures = $ul.find('ul');
            for (var i = 0; i < data.failures.length; i++) {
                var number = data.failures[i][0],
                     who = data.failures[i][1];
                $ul_failures.append('<li><strong>#' + number + '</strong> is being updated by <strong>' + who + '</strong></li>');
            }
        }
        this.$modal.find('.btn-confirm').replaceWith('<button class="btn btn-blue" data-dismiss="modal">Close</button>');
        this.$modal.data('modal').options.keyboard = true;
        $('.ms-action.ms-' + this.action + ' .ms-action-reset').click();
    }); // IssuesList_multiselect_confirm_done

    IssuesList.multiselect_confirm_failed = (function IssuesList_multiselect_confirm_failed () {
        this.$modal.find('.modal-body').empty().append('<div class="alert alert-error">There was an error while processing your request.</div>');
        this.$modal.find('.btn-confirm').replaceWith('<button class="btn btn-blue" data-dismiss="modal">Close</button>');
        this.$modal.data('modal').options.keyboard = true;
        $('.ms-action.ms-' + this.action + ' .ms-action-apply').removeClass('disabled').removeAttr('title');
        $('.ms-action.ms-' + this.action + ' input').iCheck('enable').removeAttr('title');
    }); // IssuesList_multiselect_confirm_failed

    IssuesList.get_multiselect_action_confirm_modal_node = (function IssuesList_get_multiselect_action_confirm_modal_node () {
        var $template = $('#main .ms-action-confirm-modal');
        if (!$template.length) {
            $template = $('\
                <div class="modal fancy template hide ms-action-confirm-modal">\
                    <div class="modal-header"><h6></h6></div>\
                    <div class="modal-body">\
                    <ul></ul>\
                    </div>\
                    <div class="modal-footer">\
                        <div class="row-fluid auto-align">\
                            <div class="span6">\
                                <button class="btn btn-blue btn-loading btn-confirm">Confirm <i class="fa fa-spinner fa-spin"> </i></button>\
                            </div>\
                            <div class="span6">\
                                <button class="btn btn-default" data-dismiss="modal">Cancel</button>\
                            </div>\
                        </div>\
                    </div>\
                </div>\
            ');
            $('#main').append($template);
        }

        var $result = $template.clone();
        $result.attr('style', '').removeClass('template');
        return $result;


    }); // IssuesList_get_multiselect_action_confirm_modal_node

    IssuesList.on_ms_action_choice_click = (function IssuesList_on_ms_action_choice_click (ev) {
        var $input = $(this).find('input');
        if (!$input.prop('disabled')) {
            $input.iCheck('toggle');
        }
        ev.stopPropagation();
    }); // IssuesList_on_ms_action_choice_click

    IssuesList.on_ms_action_choice_keyboard_activate = (function IssuesList_on_ms_action_choice_keyboard_activate (ev) {
        var $link = $(ev.target).closest('.multiselect-info .ms-action-choice');
        if ($link.length) {
            IssuesList.on_ms_action_choice_click.bind($link[0])(ev);
            ev.stopPropagation();
            return false;
        }
    }); // IssuesList_on_ms_action_choice_keyboard_activate

    IssuesList.on_ms_action_focus_search_input = (function IssuesList_on_ms_action_focus_search_input (ev) {
        var $this = $(ev.target);
        if ($this.is('input')) { return; }
        var $dropdown = $this.closest('.ms-action');
        if ($dropdown.length) {
            $dropdown.find('.quicksearch-widget input').focus();
            ev.stopPropagation();
            return false;
        }
    });

    IssuesList.on_ms_action_go_up_from_first_item = (function IssuesList_on_ms_action_go_up_from_first_item (ev) {
        var $this = $(ev.target);
        if ($this.is('a') && $this.is('.ms-action-choice a')) {
            var $dropdown = $this.closest('.dropdown');
            if ($dropdown.find('.ms-action-choice:not(.hidden) a').first()[0] == $this[0]) {
                var $quicksearch = $dropdown.find('.quicksearch');
                if ($quicksearch.length) {
                    $quicksearch.focus();
                    ev.stopPropagation();
                    return false;
                }
            }
        }
    });

    IssuesList.on_ms_action_checkbox_indeterminate_selector_toggled = (function IssuesList_on_ms_action_checkbox_indeterminate_selector_toggled (ev) {
        // cycle: indeterminate => checked => unchecked => indeterminate => ...
        var $input = $(this);
        if (!$input.prop('checked')) {
            $input.data('previously-indeterminate', false);
        } else {
            if (!$input.data('previously-indeterminate')) {
                $input.iCheck('indeterminate');
                $input.data('previously-indeterminate', true);
            } else {
                $input.data('previously-indeterminate', false);
            }
        }
    }); // IssuesList_on_ms_action_checkbox_indeterminate_selector_toggled

    IssuesList.on_ms_action_radio_selector_toggled = (function IssuesList_on_ms_action_radio_selector_toggled (ev) {
        var $input = $(this);
        if ($input.prop('checked')) {
            $input.closest('.dropdown-menu').find('input[name=' + $input.attr('name') + ']').iCheck('determinate');
        }
    });

    IssuesList.init_all();
    window.IssuesList = IssuesList;

    var IssuesFilters = {
        selector: '.issues-filters',
        lists_count: 0,
        on_filter_show: (function IssuesFilters__on_filter_show (ev) {
            $(ev.target).siblings('[data-toggle=collapse]').children('i').removeClass('fa-caret-right').addClass('fa-caret-down');
        }), // on_filter_show
        on_filter_shown: (function IssuesFilters__on_filter_shown (ev) {
            var $collapse = $(ev.target);
            if ($collapse.hasClass('deferred')) {
                $collapse.trigger('reload');
                ev.stopPropagation();
            } else {
                IssuesFilters.focus_quicksearch_filter($collapse);
            }
        }), // on_filter_shown
        on_filter_hide: (function IssuesFilters__on_filter_hide (ev) {
            $(ev.target).siblings('[data-toggle=collapse]').children('i').removeClass('fa-caret-down').addClass('fa-caret-right');
        }), // on_filter_hide
        on_deferrable_loaded: (function IssuesFilters__on_deferrable_loaded (ev) {
            IssuesFilters.focus_quicksearch_filter($(ev.target));
        }), // on_deferrable_loaded
        focus_quicksearch_filter: (function IssuesFilters__focus_quicksearch_filter ($filter_node) {
            $filter_node.find('input.quicksearch').focus();
        }), // focus_quicksearch_filter
        add_waiting: (function IssuesFilters__add_waiting ($node) {
            var $mask = $node.children('.loading-mask');
            if (!$mask.length) {
                $mask = $('<div class="loading-mask"><p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p></div>');
                $node.append($mask);
            } else {
                $mask.removeClass('no-spinner');
                $mask.show();
            }
            return $mask;
        }), // add_waiting
        remove_waiting: (function IssuesFilters__remove_waiting ($node) {
            $node.children('.loading-mask').hide();
        }), // remove_waiting
        on_filter_click: (function IssuesFilters__on_filter_click () {
            var $filters_node = $(this).closest(IssuesFilters.selector), $issues_list_node;
            if ($filters_node.attr('id') == 'issues-filters-board-main') {
                return;
            }
            $issues_list_node = $filters_node.next(IssuesList.container_selector);
            return IssuesFilters.reload_filters_and_list(this.href, $filters_node, $issues_list_node)
        }), // on_filter_click
        on_list_filter_click: (function IssuesFilters__on_list_filter_click_click () {
            var $issues_list_node = $(this).closest(IssuesList.container_selector), $filters_node;
            if (!$issues_list_node.length && IssuesList.current) {
                $issues_list_node = IssuesList.current.$container_node;
            }
            if (!$issues_list_node.length) {
                // no list for this link, let the click load the issues page
                return true;
            }

            if (UrlParser.parse(this.href).pathname != $issues_list_node[0].IssuesList.base_url) {
                // the base url of the list is different, let the click load the issues page
                return true;
            }

            if (window.ChartManager) {
                window.ChartManager.close_chart();
            }

            $filters_node = $issues_list_node.prev(IssuesFilters.selector);
            return IssuesFilters.reload_filters_and_list(this.href, $filters_node, $issues_list_node);
        }), // on_list_filter_click
        reload_filters_and_list: (function IssuesFilters__reload_filters_and_list (url, $filters_node, $issues_list_node, no_history) {

            if (typeof no_history === 'undefined' ) {
                no_history = (IssuesFilters.lists_count > 1);
            }

            var fail_callback = function(xhr, data) {
                if (IssuesFilters.lists_count > 1) {
                    var $container = IssuesFilters.add_waiting($issues_list_node).children('.empty-area'),
                        $spin = $container.children('i'),
                        $alert = $container.children('.alert'),
                        $button;
                    if ($alert.length) {
                        $alert.children('.btn');
                        $alert.show();
                    } else {
                        $button = $('<a class="btn btn-mini btn-default" href="#">Try again</a>');
                        $alert = $('<div class="alert alert-error">The list couldn\'t be loaded.</div>').append($button);
                        $container.append($alert);
                        $button.on('click', Ev.stop_event_decorate(function() {
                            $alert.hide();
                            $spin.show();
                            IssuesFilters.reload_filters_and_list(url, $filters_node, $issues_list_node, no_history);
                            return false;
                        }));
                    }
                    $spin.hide();
                } else {
                    window.location.href = url;
                }
            };

            var list_index = IssuesList.get_index_for_node($issues_list_node.children(IssuesList.selector)),
                context = {
                    '$filters_node': $filters_node,
                    '$issues_list_node': $issues_list_node,
                    list_index: list_index,
                    url: url,
                    no_history: no_history,
                    fail_callback: fail_callback
                };

            $.get(url)
                .done($.proxy(IssuesFilters.on_filters_and_list_loaded, context))
                .fail($.proxy(fail_callback, context));

            IssuesFilters.add_waiting($filters_node);
            IssuesFilters.add_waiting($issues_list_node);

            return false;
        }), // reload_filters_and_list

        on_filters_and_list_loaded: (function IssuesFilters_on_filters_and_list_loaded (data) {
            var $data = $(data),
                $new_filters_node = $data.filter(IssuesFilters.selector),
                $new_issues_list_node = $data.filter(IssuesList.container_selector),
                current_list;

            try {
                current_list = IssuesList.all[this.list_index];
            } catch(e) {
                current_list = null;
            }
            if (!current_list) {
                $.proxy(this.fail_callback, this)(data);
                return;
            }

            current_list.$container_node.removeClass('multiselect-mode');

            if (!this.no_history && IssuesList.all.length == 1) {
                HistoryManager.add_history(this.url);
            }

            $new_filters_node.find('.deferrable').deferrable();
            $new_issues_list_node.find('.deferrable').deferrable();

            this.$filters_node.replaceWith($new_filters_node);
            this.$issues_list_node.replaceWith($new_issues_list_node);

            current_list.replace_by_node($new_issues_list_node.children(IssuesList.selector));

            return current_list;

        }), // on_filters_and_list_loaded

        init: function() {
            var active = false;
            IssuesFilters.lists_count = $(IssuesFilters.selector).length;
            if (IssuesFilters.lists_count) {
                $document.on({
                    'show.collapse': IssuesFilters.on_filter_show,
                    'shown.collapse': IssuesFilters.on_filter_shown,
                    'hide.collapse': IssuesFilters.on_filter_hide,
                    'reloaded': IssuesFilters.on_deferrable_loaded
                }, IssuesFilters.selector)
                    .on('click', IssuesFilters.selector + ' .filters-toggler', Ev.cancel)
                    .on('click', IssuesFilters.selector + ' a:not(.accordion-toggle):not(.filters-toggler)', Ev.stop_event_decorate(IssuesFilters.on_filter_click));
                active = true;
            }
            if (IssuesList.all.length) {
                $document.on('click', '.dropdown-sort ul a, .dropdown-groupby ul a, .dropdown-metric ul a, .metric-stats a:not(.milestone-graph-link), a.no-limit-btn',
                    Ev.stop_event_decorate_dropdown(IssuesFilters.on_list_filter_click));
                active = true;
            }
        } // init
    };
    IssuesFilters.init();
    window.IssuesFilters = IssuesFilters;

    var $IssueByNumberWindow = $('#go-to-issue-window');
    var IssueByNumber = {
        $window: $IssueByNumberWindow,
        $form: $IssueByNumberWindow.find('form'),
        $input: $IssueByNumberWindow.find('form input'),
        open: (function IssueByNumber_open () {
            $body.append(IssueByNumber.$window); // move at the end to manage zindex
            IssueByNumber.$window.modal('show');
            return false; // stop event propagation
        }), // IssueByNumber_open
        on_show: (function IssueByNumber_on_show () {
            IssueByNumber.$input.val('');
        }), // IssueByNumber_on_show
        on_shown: (function IssueByNumber_on_shown () {
            setTimeout(function() {
                IssueByNumber.$input.focus();
                IssueByNumber.$input.prop('placeholder', "Type an issue number");
            }, 250);
        }), //IssueByNumber_on_shown
        on_submit: (function IssueByNumber_on_submit () {
            var number = IssueByNumber.$input.val(),
                fail = false;
            if (!number) {
                fail = true;
            } else if (number[0] == '#') {
                number = number.slice(1);
            }
            IssueByNumber.$input.val('');
            if (!fail && !isNaN(number)) {
                IssueByNumber.$window.modal('hide');
                IssueByNumber.$input.prop('placeholder', "Type an issue number");
                IssueByNumber.open_issue({
                    number: number,
                    repository: main_repository
                });
            } else {
                IssueByNumber.$input.prop('placeholder', "Type a correct issue number");
            IssueByNumber.$input.focus();
            }
            return false; // stop event propagation
        }), // IssueByNumber_on_submit
        open_issue: (function IssueByNumber_open_issue (issue_ident) {
            IssuesListIssue.open_issue(issue_ident, !IssueDetail.$main_container.length);
        }), // IssueByNumber_open_issue
        init_events: (function IssueByNumber_init_events () {
            if (!IssueByNumber.$window.length) { return; }
            $document.on('keypress', Ev.key_decorate(Ev.charcode(35, IssueByNumber.open)));  // 35 = #
            jwerty.key('i', Ev.key_decorate(IssueByNumber.open));
            IssueByNumber.$window.on('show.modal', IssueByNumber.on_show);
            IssueByNumber.$window.on('shown.modal', IssueByNumber.on_shown);
            IssueByNumber.$form.on('submit', Ev.stop_event_decorate(IssueByNumber.on_submit));
        }) // IssueByNumber_init_events
    }; // IssueByNumber

    IssueByNumber.init_events();

    var toggle_full_screen_for_current_modal = (function toggle_full_screen_for_current_modal() {
        var $modal = $('.modal.in');
        if ($modal.length) {
            if ($modal.length > 1) {
                // get one with higher z-index
                $modal = $($modal.sort(function(a, b) { return $(b).css('zIndex') - $(a).css('zIndex'); })[0]);
            }
            $modal.toggleClass('full-screen');
            //noinspection RedundantIfStatementJS
            if (IssueDetail.is_modal_an_IssueDetail($modal)) {
                // continue to IssueDetail.toggle_full_screen if the modal is a IssueDetail
                return true;
            }
            return false; // stop event propagation
        }
    }); // toggle_full_screen_for_current_modal
    jwerty.key('s', Ev.key_decorate(toggle_full_screen_for_current_modal));

    var on_help = (function on_help() {
        $('#show-shortcuts').first().click();
        return false; // stop event propagation
    }); // on_help

    if ($('#shortcuts-window').length) {
        $document.on('keypress', Ev.key_decorate(Ev.charcode(63, on_help)));  // 63 = ?
    }

    var IssueDetail = {
        $main_container: $('#main-issue-container'),
        $modal: $('#modal-issue-view'),
        $modal_body: null,  // set in __init__
        $modal_container: null,  // set in __init__
        WS_subscribed_ident: null,  // ident issue currently tracked by WS

        get_url_for_ident: (function IssueDetail__get_url_for_ident (issue_ident) {
            var number = issue_ident.number.toString(),
                result = '/' + issue_ident.repository + '/issues/';
            if (number.indexOf('pk-') == 0) {
                if (!issue_ident.repository) {
                    result = '/issue/' + number.substr(3);
                } else {
                    result += 'created/' + number.substr(3);
                }
            } else {
                result += number;
            }
            return result + '/';
        }), // get_url_for_ident

        on_issue_loaded: (function IssueDetail__on_issue_loaded ($node, focus_modal) {
            var is_modal = IssueDetail.is_modal($node),
                complete_issue_ident = IssueDetail.get_issue_ident($node.children('.issue-content'));
            if (!complete_issue_ident.number) {
                complete_issue_ident.number = 'pk-' + complete_issue_ident.id;
            }
            IssueDetail.set_issue_ident($node, complete_issue_ident);
            if (is_modal && focus_modal) {
                // focusing $node doesn't FUCKING work
                setTimeout(function() {
                    $node.find('header h3 a').focus();
                }, 250);
            }
            // display the repository name if needed
            $node.toggleClass('with-repository', $node.data('repository') != main_repository);
            // set waypoints
            IssueDetail.set_issue_waypoints($node, is_modal);
            IssueDetail.scroll_tabs($node, true);
            IssueDetail.subscribe_updates($node);
            HistoryManager.add_history(null, complete_issue_ident.id, is_modal);
        }), // on_issue_loaded

        get_scroll_context: (function IssueDetail__get_scroll_context ($node, is_modal) {
            if (typeof is_modal === 'undefined') {
                is_modal = IssueDetail.is_modal($node);
            }
            return is_modal ? $node.parent() : $node;
        }), // get_scroll_context

        get_repository_name_height: (function IssueDetail__get_repository_name_height ($node) {
            return $node.hasClass('with-repository') ? 30 : 0;
        }), // get_repository_name_height

        set_issue_waypoints: (function IssueDetail__set_issue_waypoints ($node, is_modal) {
            var issue_ident = IssueDetail.get_issue_ident($node);
            $node.removeClass('header-stuck');
            setTimeout(function() {
                if (!IssueDetail.is_issue_ident_for_node($node, issue_ident)) { return; }
                var $context = IssueDetail.get_scroll_context($node, is_modal);
                $node.find(' > .issue-content > .area-top header').waypoint('sticky', {
                    context: $context,
                    wrapper: '<div class="sticky-wrapper area-top-header-sticky-wrapper" />',
                    stuckClass: 'area-top stuck',
                    handler: function(direction) {
                        $node.toggleClass('header-stuck', direction == 'down');
                    }
                });
                IssueDetail.set_tabs_waypoints($node);
            }, 500);
        }), // set_issue_waypoints

        set_tabs_waypoints: (function IssueDetail__set_tabs_waypoints ($node, $context) {
            var $tabs = $node.find('.issue-tabs');
            if ($tabs.length) {
                if (typeof $context == 'undefined') {
                    $context = IssueDetail.get_scroll_context($node);
                }
                $tabs.waypoint('sticky', {
                    context: $context,
                    wrapper: '<div class="sticky-wrapper issue-tabs-sticky-wrapper" />',
                    stuckClass: 'area-top stuck',
                    offset: 47 + IssueDetail.get_repository_name_height($node), // stuck header height
                    handler: function() {
                        setTimeout(function() { IssueDetail.scroll_tabs($node); }, 500);
                    }
                })
            }
        }), // IssueDetail__set_tabs_waypoints

        set_tab_files_waypoints: (function IssueDetail__set_tab_files_waypoints ($node, $tab_pane, $context) {
            var $files_list_container = $tab_pane.find('.code-files-list-container');
            if ($files_list_container.length) {
                if (!$context) {
                    $context = IssueDetail.get_scroll_context($node);
                }
                $files_list_container.waypoint('sticky', {
                    context: $context,
                    wrapper: '<div class="sticky-wrapper files-list-sticky-wrapper" />',
                    offset: 47 + 37 + IssueDetail.get_repository_name_height($node)  // 47 for stuck header height + 37 for stuck tabs height
                });
            }
        }), // set_tab_files_waypoints

        set_tab_review_waypoints: (function IssueDetail__set_tab_review_issue_waypoints ($node, $tab_pane, $context) {
            var $review_header = $tab_pane.find('.review-header');
            if ($review_header.length) {
                if (!$context) {
                    $context = IssueDetail.get_scroll_context($node);
                }
                $review_header.waypoint('sticky', {
                    context: $context,
                    wrapper: '<div class="sticky-wrapper review-header-sticky-wrapper" />',
                    offset: 47 + 37 + IssueDetail.get_repository_name_height($node)  // 47 for stuck header height + 37 for stuck tabs height
                });
            }
        }), // set_tab_review_issue_waypoints

        unset_issue_waypoints: (function IssueDetail__unset_issue_waypoints ($node) {
            $node.find(' > .issue-content > .area-top header').waypoint('unsticky');
            IssueDetail.unset_tabs_waypoints($node);
            $node.find('.code-files-list-container').each(function() {
                $(this).waypoint('unsticky');
            });
            $node.find('.review-header').each(function() {
                $(this).waypoint('unsticky');
            });
        }), // unset_issue_waypoints

        unset_tabs_waypoints: (function IssueDetail__unset_tabs_waypoints ($node) {
            var $tabs = $node.find('.issue-tabs');
            if ($tabs.length) {
                $tabs.waypoint('unsticky');
            }
        }), // IssueDetail__unset_tabs_waypoints

        unset_tab_files_waypoints: (function IssueDetail__unset_tab_files_waypoints ($tab_pane) {
            $tab_pane.find('.code-files-list-container').waypoint('unsticky');
        }), // unset_tab_files_waypoints

        unset_tab_review_waypoints: (function IssueDetail__unset_tab_review_waypoints ($tab_pane) {
            $tab_pane.find('.review-header').waypoint('unsticky');
        }), // unset_tab_review_waypoints

        reload_waypoints: (function IssueDetail__reload_waypoints($node) {
            IssueDetail.unset_tabs_waypoints($node);
            IssueDetail.set_tabs_waypoints($node);
            var $files_tab_pane = $($node.find('.pr-files-tab:not(.template) a').attr('href'));
            if ($files_tab_pane.length && $files_tab_pane.data('files-list-loaded')) {
                IssueDetail.unset_tab_files_waypoints($files_tab_pane);
                IssueDetail.set_tab_files_waypoints($files_tab_pane);
            }
            var $review_tab_pane = $($node.find('.pr-review-tab:not(.template) a').attr('href'));
            if ($review_tab_pane.length && $review_tab_pane.data('review-loaded')) {
                IssueDetail.unset_tab_review_waypoints($review_tab_pane);
                IssueDetail.set_tab_review_waypoints($review_tab_pane);
            }
        }), // IssueDetail__reload_waypoints

        on_statuses_or_review_box_toggled: (function IssueDetail__on_statuses_or_review_box_box_toggled (ev) {
            if (ev.target != this) { return; }
            var $node =  $(this).closest('.issue-container');
            if ($node.length) {
                IssueDetail.reload_waypoints($node);
            }
        }), // IssueDetail__on_statuses_or_review_box_box_toggled

        on_statuses_box_logs_toggled: (function IssueDetail__on_statuses_box_logs_toggled () {
            var $node =  $(this).closest('.issue-container');
            if ($node.length) {
                IssueDetail.reload_waypoints($node);
            }
            return false;
        }), // IssueDetail__on_statuses_box_logs_toggled

        on_statuses_box_older_logs_toggled: (function IssueDetail__on_statuses_box_older_logs_toggled () {
            var $node =  $(this).closest('.issue-container');
            $(this.parentNode).addClass('show-older');
            if ($node.length) {
                IssueDetail.reload_waypoints($node);
            }
            return false;
        }), // IssueDetail__on_statuses_box_older_logs_toggled

        is_modal: (function IssueDetail__is_modal ($node) {
            return !!$node.data('$modal');
        }), // is_modal

        enhance_modal: (function IssueDetail__enhance_modal ($node) {
            $node.find('.issue-nav ul').append('<li class="divider"></li><li><a href="#" data-dismiss="modal"><i class="fa fa-times fa-fw"> </i> Close window</a></li>');
        }), // enhance_modal

        get_container: (function IssueDetail__get_container (force_popup) {
            var panel = {
                $window: null,
                $node: IssueDetail.$main_container,
                $scroll_node: IssueDetail.$main_container,
                after: null
            }, popup = {
                $window: IssueDetail.$modal,
                $node: IssueDetail.$modal_container,
                $scroll_node: IssueDetail.$modal_body,
                after: IssueDetail.enhance_modal
            };
            return (force_popup || !IssueDetail.$main_container.length) ? popup : panel;
        }), // get_container

        is_issue_ident_for_node: (function IssueDetail__is_issue_ident_for_node($node, issue_ident) {
            var existing_ident = IssueDetail.get_issue_ident($node);
            return (existing_ident.number == issue_ident.number && (existing_ident.repository || '') == (issue_ident.repository || ''));
        }), // is_issue_ident_for_node

        get_issue_ident: (function IssueDetail__get_issue_ident($node) {
            return {
                number: $node.data('issue-number'),
                id: $node.data('issue-id'),
                repository: $node.data('repository'),
                repository_id: $node.data('repository-id')
            };
        }), // get_issue_ident

        set_issue_ident: (function IssueDetail__set_issue_ident($node, issue_ident) {
            if (issue_ident.number && issue_ident.repository) {
                var actual_ident = IssueDetail.get_issue_ident($node);
                if (actual_ident.number && actual_ident.repository) {
                    if (actual_ident.number != issue_ident.number || actual_ident.repository != issue_ident.repository) {
                        IssueDetail.unsubscribe_updates($node);
                    }
                }
            }
            $node.data('issue-number', issue_ident.number);
            $node.data('issue-id', issue_ident.id);
            $node.data('repository', issue_ident.repository);
            $node.data('repository-id', issue_ident.repository_id);
        }), // set_issue_ident

        get_container_waiting_for_issue: (function IssueDetail__get_container_waiting_for_issue (issue_ident, force_popup, force_load) {
            var container = IssueDetail.get_container(force_popup),
                is_popup = (force_popup || container.$window);
            if (!force_load && !is_popup && IssueDetail.is_issue_ident_for_node(container.$node, issue_ident)) {
                return false;
            }
            IssueDetail.set_issue_ident(container.$node, issue_ident);
            if (container.$window && !container.$window.hasClass('in')) {
                IssueDetail.show_modal();
            }
            return container;
        }), // get_container_waiting_for_issue

        show_modal: (function IssueDetail__show_modal () {
            var container = IssueDetail.get_container(true);
            container.$window.addClass('full-screen');
            container.$node.addClass('big-issue');
            // Move the modal at the end of all nodes to make it over in z-index
            $body.append(container.$window);
            // open the popup with its loading spinner
            container.$window.modal("show");
        }), // IssueDetail__show_modal

        hide_modal: (function IssueDetail__hide_modal () {
            var container = IssueDetail.get_container(true);
            if (container.$window.data('modal')) {
                container.$window.modal("hide");
            }
        }), // IssueDetail__hide_mocal

        get_containers_for_ident: (function IssueDetail__get_containers_for_ident (issue_ident) {
            return $('.issue-container:visible').filter(function() {
                var $this = $(this),
                    container_issue_ident = IssueDetail.get_issue_ident($this);

                // If we have the issue id, it's easy
                if (issue_ident.id && container_issue_ident.id) {
                    return (issue_ident.id == container_issue_ident.id);
                }

                // Without id we must have the number
                if (issue_ident.number && container_issue_ident.number) {
                    if (issue_ident.number != container_issue_ident.number) {
                        return false;
                    }
                } else {
                    // cannot know if no id and number
                    return false;
                }

                // The number is ok, check the repository
                if (issue_ident.repository_id && container_issue_ident.repository_id) {
                    return (issue_ident.repository_id != container_issue_ident.repository_id);
                }
                if (issue_ident.repository && container_issue_ident.repository) {
                    return (issue_ident.repository != container_issue_ident.repository);
                }

                // no repository, we cannot say
                return false;
            })
        }), // IssueDetail__get_containers_for_ident

        mark_containers_nodes_as_updated: (function IssueDetail__mark_containers_as_updated ($nodes, issue_type) {
            for (var i = 0; i < $nodes.length; i++) {
                IssueDetail.mark_container_node_as_updated($($nodes[i]), issue_type);
            }
        }), // IssueDetail__mark_containers_as_updated

        mark_container_node_as_updated: (function IssueDetail__mark_container_node_as_updated ($node, issue_type) {
            var $holder = $node.find('header > h3').first(),
                $marker = $holder.children('.updated-marker');

            if (!$marker.length) {
                $marker = $('<a class="updated-marker refresh-issue" href="#" title="' + 'This ' + issue_type + ' was updated. Click to reload.' + '"><span>[</span>updated<span>]</span></a>');
                $holder.prepend($marker);
            }
        }), // IssueDetail__mark_container_as_updated

        refresh_created_issue: (function IssueDetail__refresh_created_issue (front_uuid) {
            var $containers = $('.issue-container:visible');
            for (var i = 0; i < $containers.length; i++) {
                var $container = $($containers[i]);
                if ($container.children('.issue-content').data('front-uuid') == front_uuid) {
                    IssueDetail.refresh({$node: $container});
                }
            }
        }), // IssueDetail__refresh_created_issue

        fill_container: (function IssueDetail__fill_container (container, html) {
            if (typeof $().select2 != 'undefined') {
                container.$node.find('select.select2-offscreen').select2('destroy');
            }
            container.$node.html(html);
            container.$scroll_node.scrollTop(1);  // to move the scrollbar (WTF !)
            container.$scroll_node.scrollTop(0);
        }), // fill_container

        display_issue: (function IssueDetail__display_issue (html, issue_ident, force_popup) {
            var container = IssueDetail.get_container(force_popup);
            if (!this.is_issue_ident_for_node(container.$node, issue_ident)) { return; }
            IssueDetail.fill_container(container, html);
            IssueDetail.on_issue_loaded(container.$node, true);
            if (container.after) {
                container.after(container.$node);
            }
            MarkdownManager.update_links(container.$node);
        }), // display_issue

        clear_container: (function IssueDetail__clear_container (error, force_popup) {
            var container = IssueDetail.get_container(force_popup);
            IssueDetail.unset_issue_waypoints(container.$node);
            IssueDetail.set_issue_ident(container.$node, {number: 0, id: null, repository: '', repository_id: null});
            IssueDetail.fill_container(container, '<p class="empty-area">' + (error ? error + ' :(' : '...') + '</p>');
        }), // clear_container

        set_container_loading: (function IssueDetail__set_container_loading (container) {
            IssueDetail.unset_issue_waypoints(container.$node);
            IssueDetail.fill_container(container, '<p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p>');
        }), // set_container_loading

        select_tab: (function IssueDetail__select_tab (panel, type) {
            var $tab_link = panel.$node.find('.' + type + '-tab > a');
            if ($tab_link.length) { $tab_link.tab('show'); }
            return false;
        }), // select_tab
        select_discussion_tab: function(panel) { return IssueDetail.select_tab(panel, 'pr-discussion'); },
        select_commits_tab: function(panel) { return IssueDetail.select_tab(panel, 'pr-commits'); },
        select_files_tab: function(panel) { return IssueDetail.select_tab(panel, 'pr-files'); },
        select_review_tab: function(panel) { return IssueDetail.select_tab(panel, 'pr-review'); },

        on_files_list_loaded: (function IssueDetail__on_files_list_loaded ($node, $tab_pane) {
            if ($tab_pane.data('files-list-loaded')) { return; }
            $tab_pane.data('files-list-loaded', true);
            IssueDetail.set_tab_files_waypoints($node, $tab_pane);
            $tab_pane.find('.code-files-list a.path').first().click();
        }), // on_files_list_loaded

        on_files_list_click: (function IssueDetail__on_files_list_click (ev) {
            var $link = $(this),
                $target = $($link.attr('href')),
                $node = $link.closest('.issue-container'),
                $tab_pane = $link.closest('.tab-pane');
            IssueDetail.scroll_in_files_list($node, $tab_pane, $target, -20); // -20 = margin
            IssueDetail.set_active_file($tab_pane, $link.closest('tr').data('pos'), true);
            if (!ev.no_file_focus) {
                $target.find('.box-header a.path').focus();
            }
            return false;
        }), // on_files_list_click

        on_review_loaded: (function IssueDetail__on_review_loaded ($node, $tab_pane) {
            if ($tab_pane.data('review-loaded')) { return; }
            $tab_pane.data('review-loaded', true);
            IssueDetail.set_tab_review_waypoints($node, $tab_pane);
        }), // on_review_loaded

        get_sticky_wrappers_classes_for_tab: (function IssueDetail__get_sticky_wrappers_for_tab () {
            return {
                node: ['area-top-header-sticky-wrapper', 'issue-tabs-sticky-wrapper'],
                tab: ['files-list-sticky-wrapper']
            };
        }), // get_sticky_wrappers_for_tab

        compute_sticky_wrappers_height: (function IssueDetail__compute_sticky_wrappers_height ($node, $tab_pane, wrapper_classes) {
            var wrappers = [], i, j, height;
            for (i = 0; i < wrapper_classes.node.length; i++) {
                wrappers.push($node.find('.' + wrapper_classes.node[i]));
            }
            for (j = 0; j < wrapper_classes.tab.length; j++) {
                wrappers.push($tab_pane.find('.' + wrapper_classes.tab[j]));
            }
            height = $(wrappers)
                        .toArray()
                        .reduce(function(height, wrapper) {
                            var $wrapper = $(wrapper),
                                $stickable = $wrapper.children().first();
                            return height + ($stickable.hasClass('stuck') ? $stickable : $wrapper).outerHeight();
                        }, 0);
            return height;
        }), // compute_sticky_wrappers_height

        scroll_in_files_list: (function IssueDetail__scroll_in_files_list ($node, $tab_pane, $target, delta) {
            var is_modal = IssueDetail.is_modal($node),
                $context = IssueDetail.get_scroll_context($node, is_modal),
                is_list_on_top = !Math.round(parseFloat($tab_pane.find('.code-files-list-container').css('border-right-width'))),
                // is_full_screen = ($node.hasClass('big-issue')),
                sticky_wrappers = IssueDetail.get_sticky_wrappers_classes_for_tab($node, $tab_pane),
                stuck_height, position;

            if (!is_list_on_top && sticky_wrappers.tab.indexOf('files-list-sticky-wrapper') >= 0) {
                sticky_wrappers.tab.splice( sticky_wrappers.tab.indexOf('files-list-sticky-wrapper'));
            }

            stuck_height = IssueDetail.compute_sticky_wrappers_height($node, $tab_pane, sticky_wrappers);

            position = (is_modal ? $target.position().top : $target.offset().top)
                     + (is_modal ? 0 : $context.scrollTop())
                     - stuck_height
                     + (is_modal ? (is_list_on_top ? 65 : 445) : 10) // manual finding... :(
                     - 47 // top bar
                     + (delta || 0);

            $context.scrollTop(Math.round(0.5 + position));

            IssueDetail.highlight_on_scroll($target);
        }), // scroll_in_files_list

        highlight_on_scroll: (function IssueDetail__highlight_on_scroll($target, delay) {
            if (typeof delay == 'undefined') { delay = 1500; }
            $target.addClass('scroll-highlight');
            setTimeout(function() { $target.removeClass('scroll-highlight'); }, delay);
        }), // highlight_on_scroll

        on_files_list_toggle: (function IssueDetail__on_files_list_toggle () {
            var $files_list = $(this),
                $container = $files_list.closest('.code-files-list-container');
            if ($container.hasClass('stuck')) {
                $container.parent().height($container.outerHeight());
            }
            if ($files_list.hasClass('in')) {
               IssueDetail.set_active_file_visible($files_list.closest('.tab-pane'), $files_list);
            }
        }), // on_files_list_toggle

        toggle_files_list: (function IssueDetail__toggle_files_list () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active'),
                $link = $tab_pane.find('.code-files-list-container .files-list-summary');
            if ($link.length) { $link.click(); }
        }), // toggle_files_list

        on_file_mouseenter: (function IssueDetail__on_file_mouseenter () {
            var $file_node = $(this),
                $tab_pane = $file_node.closest('.tab-pane');
            IssueDetail.set_active_file($tab_pane, $file_node.data('pos'), false);
        }), // on_file_mouseenter

        get_visible_file_selector: (function IssueDetail__get_visible_files_selector ($tab_pane) {
            var reviewed_hidden = $tab_pane.hasClass('hide-reviewed');
            return reviewed_hidden ? 'tr:not(.hidden):not(.is-reviewed)' : 'tr:not(.hidden)';
        }), // get_visible_file_selector

        go_to_previous_file: (function IssueDetail__go_to_previous_file () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active'),
                $files_list = $tab_pane.find('.code-files-list'),
                $current_line = $files_list.find('tr.active'),
                $line = $current_line.prevAll(IssueDetail.get_visible_file_selector($tab_pane)).first();
            if ($line.length) {
                $line.find('a').click();
            }
            return false;
        }), // go_to_previous_file

        go_to_next_file: (function IssueDetail__go_to_next_file () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active'),
                $files_list = $tab_pane.find('.code-files-list'),
                $current_line = $files_list.find('tr.active'),
                $line = $current_line.nextAll(IssueDetail.get_visible_file_selector($tab_pane)).first();
            if ($line.length) {
                $line.find('a').click();
            }
            return false;
        }), // go_to_next_file

        on_files_filter_done: (function IssueDetail__on_files_filter_done () {
            IssueDetail.ensure_visible_file_active($(this).closest('.tab-pane'), true);
        }), // on_files_filter_done

        set_active_file: (function IssueDetail__set_active_file ($tab_pane, pos, reset_active_comment) {
            var $files_list = $tab_pane.find('.code-files-list'),
                selector = IssueDetail.get_visible_file_selector($tab_pane),
                $line;
            if (!$files_list.length) { return; }
            if (pos == '999999') {
                $line = $files_list.find('tr:last-child');
            } else {
                $line = $files_list.find('tr:nth-child('+ pos +')');
            }
            $files_list.find('tr.active').removeClass('active');
            $line.addClass('active');
            IssueDetail.set_active_file_visible($tab_pane, $files_list, $line);
            $tab_pane.find('.go-to-previous-file').parent().toggleClass('disabled', $line.prevAll(selector).length === 0);
            $tab_pane.find('.go-to-next-file').parent().toggleClass('disabled', $line.nextAll(selector).length === 0);
            if (reset_active_comment) {
                $files_list.closest('.code-files-list-container').data('active-comment', null);
                $tab_pane.find('.go-to-previous-file-comment, .go-to-next-file-comment').parent().removeClass('disabled');
            }
        }), // set_active_file

        set_active_file_visible: (function IssueDetail__set_active_file_visible ($tab_pane, $files_list, $line) {
            var line_top, line_height, list_visible_height, list_scroll;
            if (typeof $files_list == 'undefined') {
                $files_list = $tab_pane.find('.code-files-list');
            }
            // files list not opened: do nothing
            if (!$files_list.hasClass('in')) {
                return;
            }
            if (typeof $line == 'undefined') {
                $line = $files_list.find('tr.active');
            }
            // no active line: do nothing
            if (!$line.length) {
                return;
            }
            line_top = $line.position().top;
            list_scroll = $files_list.scrollTop();
            // above the visible part of the list: set it visible at top
            if (line_top < 0) {
                $files_list.scrollTop(Math.round(0.5 + list_scroll + line_top));
                return;
            }
            line_height = $line.height();
            list_visible_height = $files_list.height();
            // in the visible part: do nothing
            if (line_top + line_height < list_visible_height) {
                return;
            }
            // below the visible part: set it visible at the bottom
            $files_list.scrollTop(Math.round(0.5 + list_scroll + line_top - list_visible_height + line_height));
        }), // set_active_file_visible

        visible_files_comments: (function IssueDetail__visible_files_comments ($tab_pane) {
            var $files_list = $tab_pane.find('.code-files-list');
            if ($files_list.length) {
                return $files_list.find(IssueDetail.get_visible_file_selector($tab_pane) + ' a')
                            .toArray()
                            .reduce(function(groups, file_link) {
                                return groups.concat($(
                                    $(file_link).attr('href')
                                ).find('.code-comments').toArray());
                            }, [])
                            .concat($tab_pane.find('.global-comments').toArray());
            } else {
                return [];
            }
        }), // visible_files_comments

        go_to_previous_file_comment: (function IssueDetail__go_to_previous_file_comment () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active');
            IssueDetail.go_to_file_comment($node, $tab_pane, 'previous');
            return false;
        }), // go_to_previous_file_comment

        go_to_next_file_comment: (function IssueDetail__go_to_next_file_comment () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active');
            IssueDetail.go_to_file_comment($node, $tab_pane, 'next');
            return false;
        }), // go_to_next_file_comment

        go_to_file_comment: (function IssueDetail__go_to_file_comment ($node, $tab_pane, direction) {
            var $files_list_container = $tab_pane.find('.code-files-list-container'),
                $files_list = $tab_pane.find('.code-files-list'),
                comments = IssueDetail.visible_files_comments($tab_pane),
                current, comment, $comment, $file_node, file_pos, index, $hunk_node;
            if (!comments.length) { return; }

            current = $files_list_container.data('active-comment');

            if (current) {
                // we are on a comment, use it as a base
                index = comments.indexOf(current) + (direction === 'previous' ? -1 : +1);
            } else {
                if ($files_list.length) {
                    // we have a list of files, get index based on position
                    $file_node = $($files_list.find('tr.active a').attr('href'));
                    file_pos = $file_node.data('pos');
                    index = -1;
                    for (var i = 0; i < comments.length; i++) {
                        if ($(comments[i]).closest('.code-file').data('pos') >= file_pos) {
                            // we are at the first comment for/after the file:
                            //  - if we wanted the next, we got it
                            //  - if we wanted the previous, return it if we previously has one, else go 0
                            index = direction == 'next' ? i : (index >= 0 ? index : 0);
                            break;
                        } else if (direction == 'previous') {
                            // we are before the file, mark the one found as the last one
                            // and continue: the last one will be used when the loop end
                            // or if we pass the current file
                            index = i;
                        }
                    }
                } else {
                    // we have only one file, go to the first comment
                    index = 0;
                }
            }
            if (!((index || index === 0) && index >= 0 && index < comments.length)) {
                index = 0;
            }
            comment = comments[index];
            $comment = $(comment);
            $file_node = $comment.closest('.code-file');
            $files_list_container.data('active-comment', comment);
            IssueDetail.set_active_file($tab_pane, $file_node.data('pos'), false);

            // open collapsed hunk and file
            $file_node.children('.box-content').addClass('in');
            $hunk_node = $comment.closest('.diff-hunk-content');
            $hunk_node.addClass('in');

            IssueDetail.scroll_in_files_list($node, $tab_pane, $comment, -50);  // -20=margin, -30 = 2 previous diff lines
            $comment.focus();
            $tab_pane.find('.go-to-previous-file-comment').parent().toggleClass('disabled', index < 1);
            $tab_pane.find('.go-to-next-file-comment').parent().toggleClass('disabled', index >= comments.length - 1);
        }), // go_to_file_comment

        go_to_previous_review_comment: (function IssueDetail__go_to_previous_review_comment () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active');
            IssueDetail.go_to_review_comment($node, $tab_pane, 'previous');
            return false;
        }), // go_to_previous_review_comment

        go_to_next_review_comment: (function IssueDetail__go_to_next_review_comment () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active');
            IssueDetail.go_to_review_comment($node, $tab_pane, 'next');
            return false;
        }), // go_to_next_review_comment

        go_to_review_comment: (function IssueDetail__go_to_review_comment ($node, $tab_pane, direction) {
            var current_index = $tab_pane.data('current-index'),
                $all_blocks = $tab_pane.find('.pr-entry-point'),
                step = direction == 'next' ? 1 : -1,
                index = (typeof current_index == 'undefined' ? -1 : current_index) + step,
                $final_node, $container, do_scroll;

            if (index < 0 || index >= $all_blocks.length) { return; }

            for (var i = index; 0 <= i < $all_blocks.length; i+=step) {
                if (!$($all_blocks[i]).hasClass('hidden')) {
                    break;
                }
                index ++;
            }

            if (index < 0 || index >= $all_blocks.length) { return; }

            $final_node = $($all_blocks[index]);
            do_scroll = function() {
                IssueDetail.scroll_in_review($node, $tab_pane, $final_node, -20);
            };
            $container = $final_node.children('.collapse');
            if (!$container.hasClass('in')) {
                $container.one('shown.collapse', do_scroll);
                $container.collapse('show');
            } else {
               do_scroll();
            }
            IssueDetail.mark_current_review_comment($tab_pane, $final_node);

        }), // go_to_review_comment

        mark_current_review_comment: (function IssueDetail__mark_current_review_comment ($tab_pane, $target) {
            var $all_blocks = $tab_pane.find('.pr-entry-point'),
                $block = $target.closest('.pr-entry-point'),
                index = $all_blocks.toArray().indexOf($block[0]);
            $target.focus();
            $tab_pane.data('current-index', index);
            $tab_pane.find('.go-to-previous-review-comment').parent().toggleClass('disabled', index < 1);
            $tab_pane.find('.go-to-next-review-comment').parent().toggleClass('disabled', index >= $all_blocks.length - 1);
        }), // mark_current_review_comment

        go_to_global_comments: (function IssueDetail__go_to_global_comments () {
            var $tab_pane = $(this).closest('.tab-pane'),
                $node = $(this).closest('.issue-container'),
                $global_comments = $tab_pane.find('.global-comments');
            IssueDetail.scroll_in_files_list($node, $tab_pane, $global_comments, -50);  // -20=margin, -30 = 2 previous diff lines
            return false;
        }), // go_to_global_comments

        scroll_in_review: (function IssueDetail__scroll_in_review ($node, $tab_pane, $target, delta) {
            var is_modal = IssueDetail.is_modal($node),
                $context = IssueDetail.get_scroll_context($node, is_modal),
                sticky_wrappers = IssueDetail.get_sticky_wrappers_classes_for_tab($node, $tab_pane),
                stuck_height = IssueDetail.compute_sticky_wrappers_height($node, $tab_pane, sticky_wrappers),
                position = (is_modal ? $target.position().top : $target.offset().top)
                         + (is_modal ? 0 : $context.scrollTop())
                         - stuck_height
                         + (is_modal ? 60 : 5) // manual finding... :(
                         - 55 // review-header
                         - 47 // top bar;
                         + (delta || 0);

                $context.scrollTop(Math.round(0.5 + position));

            IssueDetail.highlight_on_scroll($target);
        }), // scroll_in_review

        toggle_locally_reviewed_file: (function IssueDetail__toggle_locally_reviewed_file ($file_node, reviewed, toggle_hunks) {
            var $button = $file_node.find('.box-toolbar .locally-reviewed').first(),
                $icon = $button.find('.fa'),
                $content = $file_node.children('.box-content'),
                pos = $file_node.data('pos'),
                $files_list = $file_node.closest('.tab-pane').find('.code-files-list'),
                $file_line, $file_title, $check_in_list, $hunk_headers, i, $hunk_header;

            $button.toggleClass('is-reviewed', reviewed)
                   .toggleClass('is-not-reviewed', !reviewed);

            $icon.toggleClass('fa-check-square-o', reviewed)
                 .toggleClass('fa-square-o', !reviewed);

            $file_node.toggleClass('is-reviewed', reviewed);
            $content.toggleClass('is-reviewed', reviewed);
            if (reviewed) {
                $content.collapse('hide')
            } else {
                if ($content.data('collapse')) {
                    $content.collapse('show');
                } else {
                    $content.addClass('in');
                }
            }

            if ($files_list.length) {
                $file_line = $files_list.find('tr:nth-child('+ pos +')');
                if ($file_line.length) {
                    $file_line.toggleClass('is-reviewed', reviewed);
                    $file_title = $file_line.children('td:nth-child(2)').find('a');
                    $check_in_list = $file_title.find('.fa-check');
                    if (reviewed) {
                        if (!$check_in_list.length) {
                            $file_title.append('<i class="fa fa-check" title="You marked this file as locally reviewed"> </i>');
                        }
                    } else {
                        $check_in_list.remove();
                    }
                }
            }

            if (toggle_hunks) {
                $hunk_headers = $file_node.find('.diff-hunk-header');
                for (i = 0; i < $hunk_headers.length; i++) {
                    $hunk_header = $($hunk_headers[i]);
                    IssueDetail.toggle_locally_reviewed_hunk($file_node, $hunk_header.find('.locally-reviewed'), $hunk_header.data('hunk-sha'), reviewed);
                }
            }

            IssueDetail.ensure_visible_file_active($file_node.closest('.tab-pane'), true);

        }), // toggle_locally_reviewed_file

        on_toggle_locally_reviewed_file_click: (function IssueDetail__on_toggle_locally_reviewed_file_click () {
            var $button = $(this),
                $file_node = $button.closest('.code-file'),
                was_reviewed = $button.hasClass('is-reviewed'),
                url = $button.data('url').replace('%s', was_reviewed ? 'unset' : 'set');

            IssueDetail.toggle_locally_reviewed_file($file_node, !was_reviewed);
            $.post(url,  {csrfmiddlewaretoken: $body.data('csrf')})
                .done(function(data) {
                    IssueDetail.toggle_locally_reviewed_file($file_node, data.reviewed, true);
                })
                .fail(function() {
                    IssueDetail.toggle_locally_reviewed_file($file_node, was_reviewed);
                });

            return false;
        }), // on_toggle_locally_reviewed_file_click

        toggle_locally_reviewed_hunk: (function IssueDetail__toggle_locally_reviewed_hunk ($file_node, $button, hunk_sha, reviewed) {
            var $icon = $button.find('.fa'),
                $content = $button.closest('.diff-hunk-header').next();

            $button.toggleClass('is-reviewed', reviewed)
                   .toggleClass('is-not-reviewed', !reviewed);

            $icon.toggleClass('fa-check-square-o', reviewed)
                 .toggleClass('fa-square-o', !reviewed);

            $content.toggleClass('is-reviewed', reviewed);
            if (reviewed) {
                $content.collapse('hide')
            } else {
                if ($content.data('collapse')) {
                    $content.collapse('show');
                } else {
                    $content.addClass('in');
                }
            }

        }), // toggle_locally_reviewed_hunk

        on_toggle_locally_reviewed_hunk_click: (function IssueDetail__on_toggle_locally_reviewed_hunk_click () {
            var $button = $(this),
                $file_node = $button.closest('.code-file'),
                hunk_sha = $button.closest('.diff-hunk-header').data('hunk-sha'),
                was_reviewed = $button.hasClass('is-reviewed'),
                url = $button.data('url').replace('%s', was_reviewed ? 'unset' : 'set');

            IssueDetail.toggle_locally_reviewed_hunk($file_node, $button, hunk_sha, !was_reviewed);
            $.post(url,  {csrfmiddlewaretoken: $body.data('csrf')})
                .done(function(data) {
                    IssueDetail.toggle_locally_reviewed_hunk($file_node, $button, hunk_sha, data.reviewed);
                    IssueDetail.toggle_locally_reviewed_file($file_node, data.file_reviewed);
                })
                .fail(function() {
                    IssueDetail.toggle_locally_reviewed_hunk($file_node, $button, hunk_sha, was_reviewed);
                });

            return false;

        }), // on_toggle_locally_reviewed_hunk_click

        visible_files: (function IssueDetail__visible_files($tab_pane) {
            var $links = $tab_pane.find('.code-files-list ' + IssueDetail.get_visible_file_selector($tab_pane) + ':not([data-pos=999999]) a'),
                i, files = [];

            if ($links.length) {
                for (i = 0; i < $links.length; i++) {
                    files.push($($($links[i]).attr('href')));
                }
            }

            return files;
        }),

        set_or_unset_all_visible_reviewed_status: (function IssueDetail__set_or_unset_all_visible_reviewed_status (trigger, mark_reviewed) {
            var $files = IssueDetail.visible_files($(trigger).closest('.tab-pane')),
                i, $reviewed_button, is_reviewed;

            if ($files.length) {
                mark_reviewed = !!mark_reviewed;
                for (i = 0; i < $files.length; i++) {
                    $reviewed_button = $files[i].children('.box-header').find('.locally-reviewed');
                    is_reviewed = !!$reviewed_button.hasClass('is-reviewed');
                    if (mark_reviewed != is_reviewed) {
                        IssueDetail.on_toggle_locally_reviewed_file_click.bind($reviewed_button[0])();
                    }
                }
            }

            return false;
        }), // set_or_unset_all_visible_reviewed_status

        mark_all_visible_as_reviewed: (function IssueDetail__mark_all_visible_as_reviewed() {
            return IssueDetail.set_or_unset_all_visible_reviewed_status(this, true);
        }), // mark_all_visible_as_reviewed

        mark_all_visible_as_not_reviewed: (function IssueDetail__mark_all_visible_as_not_reviewed() {
            return IssueDetail.set_or_unset_all_visible_reviewed_status(this, false);
        }), // mark_all_visible_as_not_reviewed

        ensure_visible_file_active: (function IssueDetail__ensure_visible_file_active ($tab_pane, no_file_focus) {
            var $files_list = $tab_pane.find('.code-files-list'),
                $active_file = $files_list.find('tr.active'),
                selector = IssueDetail.get_visible_file_selector($tab_pane),
                $file_to_active;

            if ($active_file.length) {
                if (!$active_file.is(selector)) {
                    $file_to_active = $active_file.nextAll(selector).first();
                    if (!$file_to_active.length) {
                        $file_to_active = $active_file.prevAll(selector).first();
                    }
                }
            } else {
                $file_to_active = $files_list.find(selector).first();
            }

            if ($file_to_active && $file_to_active.length) {
                setTimeout(function() {
                    $file_to_active.find('a').trigger({type: 'click', no_file_focus: !!no_file_focus});
                }, 100);
            }

        }), // ensure_visible_file_active

        toggle_reviewed: (function IssueDetail_toggle_reviewed() {
            var $link = $(this),
                $code_files_node = $link.closest('.code-files'),
                $icon = $link.find('.fa'),
                was_hidden = $icon.hasClass('fa-square-o'),
                now_hidden = !was_hidden;

            $code_files_node.toggleClass('hide-reviewed', now_hidden);

            $icon.toggleClass('fa-check-square-o', !now_hidden)
                 .toggleClass('fa-square-o', now_hidden);

            IssueDetail.ensure_visible_file_active($code_files_node.closest('.tab-pane'));

           return false;
        }), // toggle_reviewed

        before_load_tab: (function IssueDetail__before_load_tab (ev) {
            if (!ev.relatedTarget) { return; }
            var $previous_tab = $(ev.relatedTarget),
                $previous_target = $($previous_tab.attr('href')),
                $node = $previous_tab.closest('.issue-container'),
                is_modal = IssueDetail.is_modal($node),
                $context = IssueDetail.get_scroll_context($node, is_modal);
            $previous_target.data('scroll-position', $context.scrollTop());
        }), // before_load_tab

        scroll_tabs: (function IssueDetail__scroll_tabs($node, force_arrows, $force_tab) {
            var $tabs_scroller = $node.find('.issue-tabs'),
                $tabs_holder = $tabs_scroller.children('ul'),
                $all_tabs = $tabs_holder.children('li:visible'),
                $tab,
                current_offset, final_offset,
                tabs_holder_width, full_width,
                tab_position, tab_left, tab_right,
                $last_tab, last_tab_right,
                show_left_arrow = false, count_left = 0,
                show_right_arrow = false, count_right = 0;

            // manage tabs bar visibility
            if ($all_tabs.length == 1) {
                // tabs bar is visible but only one tab, hide the bar
                $tabs_scroller.hide();
                return;
            } else if ($all_tabs.length == 0) {
                // tabs bar seems hidden, count number of tabs that are "visible"
                // (:visible doesn't work if a parent is hidden)
                if ($tabs_holder.children('li:not(.template)').length < 2) {
                    // ok max one tab visible, keep the tabs bar hidden
                    return;
                }
                // more that one tab visible, display the tab bar
                $tabs_scroller.show();
                $all_tabs = $tabs_holder.children('li:visible');
                force_arrows = true;
            }

            // do lots of computation...
            $tab = (typeof $force_tab == 'undefined')
                    ? $tabs_holder.children('li.active')
                    : $force_tab;
            current_offset = $tabs_scroller.data('scroll-offset') || 0;
            final_offset = current_offset;
            tabs_holder_width = $tabs_scroller.innerWidth() - 50;  // padding for arrows !
            full_width = tabs_holder_width + current_offset;
            tab_position = $tab.position();
            tab_left = tab_position.left - 3;
            tab_right = tab_position.left + $tab.outerWidth() + 3;
            $last_tab = $all_tabs.last();
            last_tab_right = $last_tab.position().left + $last_tab.outerWidth() + 3;


            // fond wanted offset for tab we want to show
            if (tab_left < current_offset) {
                final_offset = tab_left;
            } else if (tab_right > full_width) {
                final_offset = current_offset + tab_right - full_width;
            } else if (last_tab_right < full_width) {
                final_offset = current_offset - (full_width - last_tab_right);
                if (final_offset < 0) { final_offset = 0; }
            }

            // apply offset the the tabs bar
            if (final_offset != current_offset) {
                if (transform_attribute) {
                    $tabs_holder.css('transform', 'translateX(' + (-final_offset) + 'px)');
                } else {
                    $tabs_holder.css('left', (-final_offset) + 'px');
                }
                $tabs_scroller.data('scroll-offset', final_offset);
            }

            // manage counters and arrows
            if (force_arrows || final_offset != current_offset) {

                // update counter of hidden tabs on the left
                if (final_offset > 0) {
                    show_left_arrow = true;
                    for (var i = 0; i < $all_tabs.length; i++) {
                        $tab = $($all_tabs[i]);
                        tab_left = $tab.position().left - 3;
                        if ( tab_left >= final_offset) {
                            break;
                        }
                        count_left += 1;
                    }
                    $tabs_scroller.data('next-left-tab', count_left ? $all_tabs[i-1]: null)
                                  .find('.scroll-left .badge').text(count_left);
                }

                // update counter of hidden tabs on the right
                full_width = tabs_holder_width + final_offset;
                if (last_tab_right > full_width) {
                    show_right_arrow = true;
                    for (var j = 0; j < $all_tabs.length; j++) {
                        $tab = $($all_tabs[j]);
                        tab_right = $tab.position().left  + $tab.outerWidth() + 3;
                        if (tab_right <= full_width) {
                            continue;
                        }
                        if (!count_right) {
                            $tabs_scroller.data('next-right-tab', $all_tabs[j]);
                        }
                        count_right += 1;
                    }
                    $tabs_scroller.find('.scroll-right .badge').text(count_right);
                    if (!count_right) {
                        $tabs_scroller.data('next-right-tab', null);
                    }
                }

                // toggle arrows visibility
                $tabs_scroller.toggleClass('no-scroll-left', !show_left_arrow)
                              .toggleClass('no-scroll-right', !show_right_arrow);

            }

        }), // scroll_tabs

        scroll_tabs_left: (function IssueDetail__scroll_tabs_left (ev) {
            var $node = $(ev.target).closest('.issue-container'),
                $tabs_scroller = $node.find('.issue-tabs'),
                next_tab = $tabs_scroller.data('next-left-tab');
            if (next_tab) {
                IssueDetail.scroll_tabs($node, false, $(next_tab));
            }
            return false;
        }), // scroll_tabs_left

        scroll_tabs_right: (function IssueDetail__scroll_tabs_right (ev) {
            var $node = $(ev.target).closest('.issue-container'),
                $tabs_scroller = $node.find('.issue-tabs'),
                next_tab = $tabs_scroller.data('next-right-tab');
            if (next_tab) {
                IssueDetail.scroll_tabs($node, false, $(next_tab));
            }
            return false;
        }), // scroll_tabs_right

        load_tab: (function IssueDetail__load_tab (ev) {
            var $tab = $(ev.target),
                $tab_pane = $($tab.attr('href')),
                tab_type = $tab_pane.data('tab'),
                is_code_tab = $tab_pane.hasClass('code-files'),
                is_review_tab = $tab_pane.hasClass('issue-review'),
                $node = $tab.closest('.issue-container'),
                is_empty = !!$tab_pane.children('.empty-area').length;

            // load content if not already available
            if (is_empty) {
                $.ajax({
                    url: $tab_pane.data('url'),
                    success: function(data) {
                        $tab_pane.html(data);
                        // adjust tabs if scrollbar
                        IssueDetail.scroll_tabs($node);
                        if (is_code_tab) {
                            IssueDetail.on_files_list_loaded($node, $tab_pane);
                        }
                        if (is_review_tab) {
                            IssueDetail.on_review_loaded($node, $tab_pane);
                        }
                        $node.trigger('loaded.tab.' + tab_type);
                    },
                    error: function() {
                        $tab_pane.children('.empty-area').html('Loading failed :(');
                    }
                });
            } else {
                if (is_code_tab) {
                    IssueDetail.on_files_list_loaded($node, $tab_pane);
                }
                if (is_review_tab) {
                    IssueDetail.on_review_loaded($node, $tab_pane);
                }
            }

            // make sure the active tab is fully visible
            IssueDetail.scroll_tabs($node);

            // if the tabs holder is stuck, we'll scroll in a cool way
            var $tabs_holder = $node.find('.issue-tabs'),
                $stuck_header, position, is_modal = IssueDetail.is_modal($node),
                $context = IssueDetail.get_scroll_context($node, is_modal),
                scroll_position = $tab_pane.data('scroll-position');
            if (scroll_position) {
                $context.scrollTop(scroll_position);
            } else if ($tabs_holder.hasClass('stuck')) {
                $stuck_header = $node.find(' > .issue-content > .area-top header');
                position = $node.find('.tab-content').position().top
                         + (is_modal ? 0 : $context.scrollTop())
                         - $stuck_header.height()
                         - $tabs_holder.height()
                         - 3; // adjust
                $context.scrollTop(Math.round(0.5 + position));
            }
            if (is_code_tab) {
                // seems to be a problem with waypoints on many files-list-containers
                $.waypoints('refresh');
            }
            if (!is_empty) {
                $node.trigger('loaded.tab.' + tab_type);
            }
        }), // load_tab

        close_tab: (function IssueDetail__close_tab (ev) {
            var $tab = $(ev.target).closest('li'),
                $tab_link = $tab.children('a'),
                $tab_pane = $($tab_link.attr('href')),
                is_active = $tab.hasClass('active'),
                $prev_tab = is_active ? $tab.prev(':visible').children('a') : null,
                $node = is_active ? null : $tab.closest('.issue-container');

            $tab.remove();
            if ($prev_tab) {
                $prev_tab.tab('show');
            } else {
                IssueDetail.scroll_tabs($node, true);
            }
            // we can only remove files tabs (commits)
            IssueDetail.unset_tab_files_waypoints($tab_pane);
            $tab_pane.remove();

            return false;
        }), // close_tab

        on_current_panel_key_event: (function IssueDetail__on_current_panel_key_event (method) {
            var decorator = function() {
                if (!PanelsSwapper.current_panel || PanelsSwapper.current_panel.obj != IssueDetail) { return; }
                return IssueDetail[method](PanelsSwapper.current_panel);
            };
            return Ev.key_decorate(decorator);
        }), // on_current_panel_key_event

        is_modal_an_IssueDetail: (function IssueDetail__is_modal_an_IssueDetail ($modal) {
            var panel = PanelsSwapper.current_panel;
            if (!panel || panel.obj != IssueDetail) { return false; }
            if (!IssueDetail.is_modal(panel.$node)) { return false; }
            return  (panel.$node.data('$modal')[0] == $modal[0]);
        }), // is_modal_an_IssueDetail

        on_main_issue_panel_key_event: (function IssueDetail__on_main_issue_panel_key_event (method) {
            var decorator = function() {
                if (!IssueDetail.$main_container.length) { return; }
                PanelsSwapper.select_panel_from_node(IssueDetail.$main_container);
                return IssueDetail[method](PanelsSwapper.current_panel);
            };
            return Ev.key_decorate(decorator);
        }), // on_main_issue_panel_key_event

        on_panel_activated: (function IssueDetail__on_panel_activated (panel) {
            if (IssuesList.current) {
                IssuesList.current.unset_current();
            }
            if (!$(document.activeElement).closest(panel.$node).length) {
                panel.$node.focus();
            }
        }), // on_panel_activated

        panel_activable: (function IssueDetail__panel_activable (panel) {
            if (!panel) { return false; }
            if (IssueDetail.is_modal(panel.$node)) {
                return panel.$node.data('$modal').hasClass('in');
            }
            //noinspection RedundantIfStatementJS
            if (!panel.$node.children('.issue-nav').length) {
                return false;
            }
            return true;
        }), // panel_activable

        on_modal_shown: (function IssueDetail__on_modal_show () {
            var $modal = $(this);
            if (PanelsSwapper.current_panel && PanelsSwapper.current_panel.$node == $modal.data('$container')) {
                return;
            }
            $modal.data('previous-panel', PanelsSwapper.current_panel);
            PanelsSwapper.select_panel_from_node($modal.data('$container'));
        }), // on_modal_show

        on_modal_hidden: (function IssueDetail__on_modal_hidden () {
            var $modal = $(this),
                $node = $modal.find('.issue-container');
            IssueDetail.unset_issue_waypoints($node);
            IssueDetail.unsubscribe_updates($node);
            PanelsSwapper.select_panel($modal.data('previous-panel'));
            $modal.data('$container').html('');

            if (IssueDetail.$main_container.length) {
                var ident = IssueDetail.get_issue_ident(IssueDetail.$main_container);
                HistoryManager.add_history(null, ident.id || false);  // false to force not getting it from the current url
            } else {
                HistoryManager.add_history(null, false);
            }
        }), // on_modal_hidden

        on_files_list_key_event:  (function IssueDetail__on_files_list_key_event (method) {
            var decorator = function() {
                if (PanelsSwapper.current_panel.obj != IssueDetail) { return; }
                var $node = PanelsSwapper.current_panel.$node,
                    $tab = $node.find('.files-tab.active');
                if (!$tab.length) { return; }
                return IssueDetail[method].call($tab);
            };
            return Ev.key_decorate(decorator);
        }), // on_files_list_key_event

        on_review_key_event:  (function IssueDetail__on_review_key_event (method) {
            var decorator = function() {
                if (PanelsSwapper.current_panel.obj != IssueDetail) { return; }
                var $node = PanelsSwapper.current_panel.$node,
                    $tab = $node.find('.pr-review-tab.active');
                if (!$tab.length) { return; }
                return IssueDetail[method].call($tab);
            };
            return Ev.key_decorate(decorator);
        }), // on_review_key_event

        focus_search_input: (function IssueDetail__focus_search_input () {
            var $node = $(this).closest('.issue-container'),
                $tab_pane = $node.find('.tab-pane.active'),
                $files_list_container = $tab_pane.find('.code-files-list-container'),
                $search_input = $files_list_container.find('input.quicksearch');
            $search_input.focus();
            return false;
        }), // focus_search_input

        toggle_full_screen: (function IssueDetail__toggle_full_screen (panel) {
            panel.$node.toggleClass('big-issue');
            IssueDetail.scroll_tabs(panel.$node, true);
            return false;
        }), // toggle_full_screen

        view_on_github: (function IssueDetail__view_on_github (panel) {
            var $link = panel.$node.find('header h3 a:not(.updated-marker)').first();
            if ($link.length) {
                window.open($link.attr('href'), '_blank');
            }
            return false;
        }), // view_on_github

        refresh: (function IssueDetail__refresh (panel) {
            var issue_ident = IssueDetail.get_issue_ident(panel.$node),
                is_popup = IssueDetail.is_modal(panel.$node);
            IssuesListIssue.open_issue(issue_ident, is_popup, true);
            return false;
        }), // refresh

        force_refresh: (function IssueDetail__force_refresh (panel) {
            var issue_ident = IssueDetail.get_issue_ident(panel.$node),
                number = issue_ident.number.toString();
            if (number.indexOf('pk-') == -1) {
                $.ajax({
                    url: '/' + issue_ident.repository + '/issues/' + number + '/ask-fetch/',
                    type: 'POST',
                    headers: {
                        'X-CSRFToken': $body.data('csrf')
                    }
                })
            }
            return false;
        }), // force_refresh

        go_to_diff_comment: (function IssueDetail__go_to_diff_comment ($issue_node, tab_name, comment_url, not_found_message) {
            var $tab_pane = $issue_node.find('.tab-pane.' + tab_name),
                $comment_node = $tab_pane.find('.issue-comment[data-url="' + comment_url + '"]'),
                $hunk_node, $file_node;
            if ($comment_node.length) {
                IssueDetail.select_tab(PanelsSwapper.get_panel_for_node($issue_node), tab_name);
                // open collapsed hunk and file
                $hunk_node = $comment_node.closest('.diff-hunk-content');
                $file_node = $hunk_node.closest('.code-diff').parent();
                $hunk_node.addClass('in');
                $file_node.addClass('in');
                // wait for tab to be shown
                setTimeout(function() {
                    // compute positioning
                    var relative_position = -20;  // some margin
                    if (IssueDetail.is_modal($issue_node)) {
                        var $container = $comment_node.closest('.code-comments');
                        relative_position += $container.position().top;
                    }
                    // and go!
                    IssueDetail.scroll_in_files_list($issue_node, $tab_pane, $comment_node, relative_position);
                }, 100);
            } else {
                alert(not_found_message);
            }
        }), // go_to_diff_comment

        on_link_to_diff_comment: (function IssueDetail__on_link_to_diff_comment () {
            var $link = $(this),
                comment_url = $link.attr('href'),
                $issue_node = $link.closest('.issue-container');

            if (!comment_url || comment_url == '#') {
                comment_url = $link.closest('.issue-comment').data('url')
            }

            $issue_node.one('loaded.tab.issue-files', function() {
                IssueDetail.go_to_diff_comment($issue_node, 'issue-files', comment_url, 'This comment is not linked to active code anymore');
            });

            IssueDetail.select_files_tab(PanelsSwapper.current_panel);
            return false;
        }), // on_link_to_diff_comment

        on_link_to_commit_diff_comment: (function IssueDetail__on_link_to_commit_diff_comment () {
            var $link = $(this),
                $entry_point = $link.closest('.pr-entry-point'),
                comment_url = $link.attr('href'),
                tab_name = 'commit-' + $entry_point.data('sha'),
                $issue_node = $link.closest('.issue-container');

            if (!comment_url || comment_url == '#') {
                comment_url = $link.closest('.issue-comment').data('url')
            }

            if (!$entry_point.length || !comment_url) {
                alert('There is a problem trying to open this commit');
            }

            $issue_node.one('loaded.tab.' + tab_name, function() {
                IssueDetail.go_to_diff_comment($issue_node, tab_name, comment_url, 'This comment could not be found');
            });

            IssueDetail.on_commit_click({target: this});
            return false
        }), // on_link_to_commit_diff_comment

        on_link_to_review_comment: (function IssueDetail__on_link_to_review_comment () {
            var $button = $(this),
                css_filter = $.map($button.data('ids'), function(id) { return '.issue-review [data-id=' + id + ']' } ).join(', '),
                $node = $button.closest('.issue-container');
            $node.one('loaded.tab.issue-review', function() {
                var $comment_node = $node.find(css_filter).first();
                if (!$comment_node.length) {
                    alert('This comment was not found, maybe a bug ;)');
                    return false;
                }
                var do_scroll = function() {
                    var $tab_pane = $node.find('.tab-pane.active'),
                        relative_position = -20; // some margin
                    IssueDetail.mark_current_review_comment($tab_pane, $comment_node);
                    if (IssueDetail.is_modal($node)) {
                        var $container = $comment_node.closest('.code-comments');
                        relative_position += $container.position().top;
                    }
                    IssueDetail.scroll_in_review($node, $tab_pane, $comment_node, relative_position);

                }; // do_scroll
                var $container = $comment_node.closest('.collapse');
                if (!$container.hasClass('in')) {
                    $container.one('shown.collapse', do_scroll);
                    $container.collapse('show');
                } else {
                   do_scroll();
                }
            });
            IssueDetail.select_review_tab(PanelsSwapper.current_panel);
            return false;
        }), // on_link_to_review_comment

        on_deleted_commits_toggle_change: (function IssueDetail__on_deleted_commits_toggle_change () {
            var $input = $(this),
                $parent = $input.closest('.issue-commits');
                $parent.toggleClass('view-deleted', $input.is(':checked'))
        }), // on_deleted_commits_toggle_change

        on_commit_click: (function IssueDetail__on_commit_click (e) {
            var $link = $(e.target),
                $holder = $link.closest('.commit-link-holder'),
                repository, sha, url,
                nb_files, nb_comments, $label_node,
                $node, tab_name;


            if (!$holder.length) {
                return;
            }

            repository = $holder.data('repository');
            $node = $holder.closest('.issue-container');

            if (repository != $node.data('repository')) {
                return;
            }

            sha = $holder.data('sha');
            tab_name = 'commit-' + sha;


            // if the tab does not exists, create it
            if (!$node.find('.' + tab_name + '-tab').length) {

                var $tab_template = $node.find('.commit-tab.template'),
                    $tab = $tab_template.clone(),
                    $tab_pane_template = $node.find('.commit-files.template'),
                    $tab_pane = $tab_pane_template.clone();

                // prepare the tab
                $tab.removeClass('template')
                    .addClass(tab_name + '-tab')
                    .attr('style', null);

                $tab.find('a').attr('href', '#' + tab_name + '-files');
                $tab.find('strong').text(sha.substring(0, 7));

                nb_files = parseInt($holder.data('files-count'), 10);
                $label_node = $tab.find('.fa-file-o');
                $label_node.next().text(nb_files);
                $label_node.parent().attr('title', nb_files + ' changed file' + (nb_files > 1 ? 's' : '' ));

                nb_comments = $holder.data('comments-count');
                $label_node = $tab.find('.fa-comments-o');
                if (nb_comments) {
                    $label_node.next().text(nb_comments);
                    $label_node.parent().attr('title', nb_comments + ' comment' + (nb_comments > 1 ? 's' : '' ));
                } else {
                    $label_node.parent().remove();
                }

                // add the tab
                $tab.insertBefore($tab_template);

                // prepare the content
                $tab_pane.removeClass('template')
                        .addClass(tab_name)
                        .attr('id', tab_name + '-files')
                        .attr('style', null)
                        .data('url', $holder.data('url'))
                        .data('comment-url', $holder.data('comment-url'))
                        .data('tab', tab_name);

                // add the content
                $tab_pane.insertBefore($tab_pane_template);

            }

            IssueDetail.select_tab(PanelsSwapper.current_panel, tab_name);

            return false;

        }), // on_commit_click

        subscribe_updates: (function IssueDetail__subscribe_updates ($node) {
            var issue_ident = IssueDetail.get_issue_ident($node);
            if (!issue_ident.repository_id || !issue_ident.id) { return; }
            var subscription = $node.data('ws-subscription');
            if (subscription) {
                if (subscription.repository_id == issue_ident.repository_id && subscription.id == issue_ident.id) {
                    return;
                }
                IssueDetail.unsubscribe_updates($node);
            }
            subscription = {
                repository_id: issue_ident.repository_id,
                id: issue_ident.id
            };
            WS.subscribe(
                'gim.front.Repository.' + subscription.repository_id + '.model.updated.isRelatedTo.Issue.' + subscription.id,
                'IssueDetail__on_update_alert',
                IssueDetail.on_update_alert,
                'exact'
            );
            WS.subscribe(
                'gim.front.Repository.' + subscription.repository_id + '.model.deleted.isRelatedTo.Issue.' + subscription.id,
                'IssueDetail__on_delete_alert',
                IssueDetail.on_delete_alert,
                'exact'
            );
            $node.data('ws-subscription', subscription);
        }), // subscribe_updates

        unsubscribe_updates: (function IssueDetail__unsubscribe_updates ($node) {
            var subscription = $node.data('ws-subscription');
            if (!subscription || !subscription.repository_id || !subscription.id) { return; }
            WS.unsubscribe(
                'gim.front.Repository.' + subscription.repository_id + '.model.updated.isRelatedTo.Issue.' + subscription.id,
                'IssueDetail__on_update_alert'
            );
            WS.unsubscribe(
                'gim.front.Repository.' + subscription.repository_id + '.model.deleted.isRelatedTo.Issue.' + subscription.id,
                'IssueDetail__on_delete_alert'
            );
            $node.removeData('ws-subscription');

        }), // unsubscribe_updates

        on_update_alert: (function IssueDetail__on_update_alert (topic, args, kwargs, subscription) {
            IssueEditor.on_update_alert(topic, args, kwargs, subscription);
        }), // on_update_alert

        on_delete_alert: (function IssueDetail__on_delete_alert (topic, args, kwargs, subscription) {
            IssueEditor.on_delete_alert(topic, args, kwargs, subscription);
        }), // on_delete_alert

        open_issue_by_id: (function IssueDetail__open_issue_by_id (issue_id, force_popup) {
            if (!force_popup && IssueDetail.$main_container.length) {
                IssueDetail.hide_modal();
                var $issue_to_select = $('#issue-' + issue_id);
                if ($issue_to_select.length && $issue_to_select[0].IssuesListIssue) {
                    $issue_to_select.removeClass('active');
                    $issue_to_select[0].IssuesListIssue.set_current(true, true);
                    return;
                }
            }
            IssuesListIssue.open_issue({
                number: 'pk-' + issue_id,
                repository: main_repository
            }, force_popup);
        }), // open_issue_by_id

        init: (function IssueDetail__init () {
            // init modal container
            IssueDetail.$modal_body = IssueDetail.$modal.children('.modal-body');
            IssueDetail.$modal_container = IssueDetail.$modal_body.children('.issue-container');
            IssueDetail.$modal_container.data('$modal', IssueDetail.$modal);
            IssueDetail.$modal.data('$container', IssueDetail.$modal_container);

            // full screen mode
            jwerty.key('s', IssueDetail.on_current_panel_key_event('toggle_full_screen'));
            jwerty.key('s', IssueDetail.on_main_issue_panel_key_event('toggle_full_screen'));
            $document.on('click', '.resize-issue', Ev.stop_event_decorate_dropdown(toggle_full_screen_for_current_modal));
            $document.on('click', '.resize-issue', IssueDetail.on_current_panel_key_event('toggle_full_screen'));

            jwerty.key('v', IssueDetail.on_current_panel_key_event('view_on_github'));
            jwerty.key('v', IssueDetail.on_main_issue_panel_key_event('view_on_github'));

            jwerty.key('r', IssueDetail.on_current_panel_key_event('refresh'));
            jwerty.key('r', IssueDetail.on_main_issue_panel_key_event('refresh'));
            $document.on('click', '.refresh-issue', Ev.stop_event_decorate_dropdown(IssueDetail.on_current_panel_key_event('refresh')));

            jwerty.key('shift+g', IssueDetail.on_current_panel_key_event('force_refresh'));
            jwerty.key('shift+g', IssueDetail.on_main_issue_panel_key_event('force_refresh'));
            $document.on('click', '.force-refresh-issue', Ev.stop_event_decorate_dropdown(IssueDetail.on_current_panel_key_event('force_refresh')));

            // tabs activation
            jwerty.key('shift+d', IssueDetail.on_current_panel_key_event('select_discussion_tab'));
            jwerty.key('shift+c', IssueDetail.on_current_panel_key_event('select_commits_tab'));
            jwerty.key('shift+f', IssueDetail.on_current_panel_key_event('select_files_tab'));
            jwerty.key('shift+r', IssueDetail.on_current_panel_key_event('select_review_tab'));
            $document.on('show.tab', '.issue-tabs a', IssueDetail.before_load_tab);
            $document.on('shown.tab', '.issue-tabs a', IssueDetail.load_tab);

            $document.on('click', '.issue-tabs:not(.no-scroll-left) .scroll-left', Ev.stop_event_decorate(IssueDetail.scroll_tabs_left));
            $document.on('click', '.issue-tabs:not(.no-scroll-right) .scroll-right', Ev.stop_event_decorate(IssueDetail.scroll_tabs_right));

            $document.on('click', '.issue-tabs .closable i.fa-times', Ev.stop_event_decorate(IssueDetail.close_tab));

            // link from PR comment in "review" tab to same entry in "files changed" tab
            $document.on('click', '.go-to-diff-link', Ev.stop_event_decorate(IssueDetail.on_link_to_diff_comment));
            $document.on('click', '.go-to-commit-diff-link', Ev.stop_event_decorate(IssueDetail.on_link_to_commit_diff_comment));

            // link from PR comment group in "discussion" tab to first entry "files changed" tab
            $document.on('click', '.go-to-review-link', Ev.stop_event_decorate(IssueDetail.on_link_to_review_comment));

            // modal events
            if (IssueDetail.$modal.length) {
                IssueDetail.$modal.on('shown.modal', IssueDetail.on_modal_shown);
                IssueDetail.$modal.on('hidden.modal', IssueDetail.on_modal_hidden);
            }

            // waypoints for loaded issue
            if (IssueDetail.$main_container.data('issue-number')) {
                IssueDetail.on_issue_loaded(IssueDetail.$main_container, false);
            }

            // commits options
            $document.on('change', '.deleted-commits-toggler input', IssueDetail.on_deleted_commits_toggle_change);
            $document.on('click', '.commit-link', Ev.stop_event_decorate(IssueDetail.on_commit_click));

            // files list summary
            $document.on('click', '.code-files-list a', Ev.stop_event_decorate(IssueDetail.on_files_list_click));
            $document.on('shown.collapse hidden.collapse', '.code-files-list', IssueDetail.on_files_list_toggle);
            $document.on('mouseenter', '.code-file', IssueDetail.on_file_mouseenter);
            jwerty.key('f', IssueDetail.on_files_list_key_event('focus_search_input'));
            jwerty.key('t', IssueDetail.on_files_list_key_event('toggle_files_list'));
            // files list navigation
            $document.on('click', 'li:not(.disabled) a.go-to-previous-file', Ev.stop_event_decorate(IssueDetail.go_to_previous_file));
            $document.on('click', 'li:not(.disabled) a.go-to-next-file', Ev.stop_event_decorate(IssueDetail.go_to_next_file));
            $document.on('quicksearch.after', '.files-filter input.quicksearch', IssueDetail.on_files_filter_done);
            $document.on('click', 'li:not(.disabled) a.go-to-previous-file-comment', Ev.stop_event_decorate(IssueDetail.go_to_previous_file_comment));
            $document.on('click', 'li:not(.disabled) a.go-to-next-file-comment', Ev.stop_event_decorate(IssueDetail.go_to_next_file_comment));
            $document.on('click', '.go-to-global-comments', Ev.stop_event_decorate_dropdown(IssueDetail.go_to_global_comments, '.btn-group'));
            $document.on('click', '.mark-visible-as-reviewed', Ev.stop_event_decorate_dropdown(IssueDetail.mark_all_visible_as_reviewed, '.btn-group'));
            $document.on('click', '.mark-visible-as-not-reviewed', Ev.stop_event_decorate_dropdown(IssueDetail.mark_all_visible_as_not_reviewed, '.btn-group'));
            $document.on('click', '.toggle-reviewed', Ev.stop_event_decorate_dropdown(IssueDetail.toggle_reviewed, '.btn-group'));
            jwerty.key('p/k', IssueDetail.on_files_list_key_event('go_to_previous_file'));
            jwerty.key('n/j', IssueDetail.on_files_list_key_event('go_to_next_file'));
            jwerty.key('shift+p/shift+k', IssueDetail.on_files_list_key_event('go_to_previous_file_comment'));
            jwerty.key('shift+n/shift+j', IssueDetail.on_files_list_key_event('go_to_next_file_comment'));

            // review navigation
            $document.on('click', 'li:not(.disabled) a.go-to-previous-review-comment', Ev.stop_event_decorate(IssueDetail.go_to_previous_review_comment));
            $document.on('click', 'li:not(.disabled) a.go-to-next-review-comment', Ev.stop_event_decorate(IssueDetail.go_to_next_review_comment));
            jwerty.key('p/k/shift+p/shift+k', IssueDetail.on_review_key_event('go_to_previous_review_comment'));
            jwerty.key('n/j/shift+n/shift+j', IssueDetail.on_review_key_event('go_to_next_review_comment'));

            // toggling statuses and review details
            $document.on('shown.collapse hidden.collapse', '.pr-commits-statuses, .pr-reviews-detail, .pr-commit-statuses .box-content', IssueDetail.on_statuses_or_review_box_toggled);
            $document.on('click', '.pr-commit-statuses .logs-toggler', Ev.stop_event_decorate(IssueDetail.on_statuses_box_logs_toggled));
            $document.on('click', '.pr-commit-statuses dl > a', Ev.stop_event_decorate(IssueDetail.on_statuses_box_older_logs_toggled));

            // only one of status details or review details
            $document.on('show.collapse', '.pr-commits-statuses', function(ev) {
                if (ev.target != this) { return; }
                var $node =  $(this).closest('.issue-container');
                if ($node.length) {
                    $node.find('.pr-review-state:not(.collapsed)').click();
                }
            });
            // only one of status details or review details
            $document.on('show.collapse', '.pr-reviews-detail', function(ev) {
                if (ev.target != this) { return; }
                var $node =  $(this).closest('.issue-container');
                if ($node.length) {
                    $node.find('.pr-last-commit-status:not(.collapsed)').click();
                }
            });

            $document.on('click', '.code-file > .box-header .locally-reviewed', Ev.stop_event_decorate(IssueDetail.on_toggle_locally_reviewed_file_click));
            $document.on('click', '.code-diff .diff-hunk-header .locally-reviewed', Ev.stop_event_decorate(IssueDetail.on_toggle_locally_reviewed_hunk_click));

        }) // init
    }; // IssueDetail
    IssueDetail.init();

    IssuesList.prototype.on_panel_activated = (function IssuesList__on_panel_activated () {
        this.set_current();
    });

    /*
        Code to pass focus from panel to panel
    */
    var PanelsSwapper = {
        events: 'click focus',
        panels: [],
        current_panel: null,
        add_handler: (function PanelsSwapper__add_handler (panel) {
            panel.$node.on(PanelsSwapper.events, {panel: panel}, PanelsSwapper.on_event);
        }), // add_handler
        remove_handler: (function PanelsSwapper__remove_handler (panel) {
            panel.$node.off(PanelsSwapper.events, PanelsSwapper.on_event);
        }), // remove_handler
        on_event: (function PanelsSwapper__on_event (ev) {
            PanelsSwapper.select_panel(ev.data.panel, ev);
        }), // on_event
        panel_activable: (function PanelsSwapper__panel_activable (panel) {
            return (panel && (!panel.obj.panel_activable || panel.obj.panel_activable(panel)));
        }), // panel_activable
        get_panel_for_node: (function PanelsSwapper__get_panel_for_node($node) {
            for (var i = 0; i < PanelsSwapper.panels.length; i++) {
                if (PanelsSwapper.panels[i].$node[0] == $node[0]) {
                    return PanelsSwapper.panels[i];
                }
            }
        }), // get_panel_for_node
        select_panel_from_node: (function PanelsSwapper__select_panel_from_node ($node) {
            var panel = PanelsSwapper.get_panel_for_node($node);
            if (panel) {
                PanelsSwapper.select_panel(panel);
            }
        }), // select_panel_from_node
        select_panel: (function PanelsSwapper__select_panel (panel) {
            if (!panel || !PanelsSwapper.panel_activable(panel)) { return; }
            if (panel.handlable) { PanelsSwapper.remove_handler(panel); }
            var old_panel = PanelsSwapper.current_panel;
            PanelsSwapper.current_panel = panel;
            if (old_panel && old_panel.handlable) { PanelsSwapper.add_handler(old_panel); }
            $('.active-panel').removeClass('active-panel');
            PanelsSwapper.current_panel.$node.addClass('active-panel');
            PanelsSwapper.current_panel.obj.on_panel_activated(PanelsSwapper.current_panel);
            return true;
        }), // select_panel
        go_prev_panel: (function PanelsSwapper__go_prev_panel() {
            if (!PanelsSwapper.current_panel.handlable) { return }
            var idx = PanelsSwapper.current_panel.index;
            while (--idx >= 0) {
                if (PanelsSwapper.panels[idx].handlable) {
                    PanelsSwapper.select_panel(PanelsSwapper.panels[idx]);
                    break;
                }
            }
            return false;
        }), // go_prev_panel
        go_next_panel: (function PanelsSwapper__go_next_panel() {
            if (!PanelsSwapper.current_panel.handlable) { return }
            var idx = PanelsSwapper.current_panel.index;
            while (++idx < PanelsSwapper.panels.length) {
                if (PanelsSwapper.panels[idx].handlable) {
                    PanelsSwapper.select_panel(PanelsSwapper.panels[idx]);
                    break;
                }
            }
            return false;
        }), // go_next_panel
        update_panel: (function PanelsSwapper__replace_panel (obj, $node) {
            var updated_panel = null;
            for (var i = 0; i < PanelsSwapper.panels.length; i++) {
                var panel = PanelsSwapper.panels[i];
                if (panel.obj == obj) {
                    updated_panel = panel;
                    panel.$node = $node;
                    break;
                }
            }
            if (updated_panel) {
                if (PanelsSwapper.current_panel==updated_panel) {
                    PanelsSwapper.current_panel.$node.addClass('active-panel');
                } else {
                    PanelsSwapper.add_handler(updated_panel);
                }
            }
        }), // update_panel
        find_panels: (function PanelsSwapper__find_panels () {
            var panels = [];
            // add all issues lists
            var $lists = $(IssuesList.selector);
            for (var i = 0; i < $lists.length; i++) {
                var issues_list = IssuesList.get_for_node($($lists[i]));
                if (!issues_list) { continue; }
                var $parent = issues_list.$node.parent(),
                    $column = $parent.parent('.board-column'),
                    is_hidden = $column.length ? $column.hasClass('hidden') : false,
                    data = {$node: $parent, obj: issues_list, handlable: true};
                if (is_hidden) {
                    data.handlable = false;
                }
                panels.push(data);
            }
            // add the main issue detail if exists
            if (IssueDetail.$main_container.length) {
                panels.push({$node: IssueDetail.$main_container, obj: IssueDetail, handlable: true});
            }
            // add the popup issue detail if exists
            if (IssueDetail.$modal_container.length) {
                panels.push({$node: IssueDetail.$modal_container, obj: IssueDetail, handlable: false});
            }
            return panels;
        }), // find_panels
        update_panels_order: (function PanelsSwapper__update_panels_order () {
            var dom_panels = PanelsSwapper.find_panels(),
                ordered_panels = [];
            for (var i = 0; i < dom_panels.length; i++) {
                var dom_panel = dom_panels[i],
                    found_panel = dom_panel,
                    found_handlable = dom_panel.handlable;
                for (var j = 0; j < PanelsSwapper.panels.length; j++) {
                    var panel = PanelsSwapper.panels[j];
                    if (panel.$node[0] == dom_panel.$node[0]) {
                        found_panel = panel;
                        found_handlable = panel.handlable;
                        break;
                    }
                }
                if (dom_panel.handlable && !found_handlable || found_panel == dom_panel ) {
                    PanelsSwapper.add_handler(found_panel);
                } else if (!dom_panel.handlable && found_handlable) {
                    PanelsSwapper.remove_handler(found_panel);
                }
                found_panel.handlable = dom_panel.handlable;
                found_panel.index = i;
                ordered_panels.push(found_panel);
            }
            PanelsSwapper.panels = ordered_panels;
            if (PanelsSwapper.current_panel && !PanelsSwapper.current_panel.handlable) {
                PanelsSwapper.current_panel.$node.removeClass('active-panel');
                PanelsSwapper.current_panel = null;
            }
            if (!PanelsSwapper.current_panel) {
                for (var k = 0; k < PanelsSwapper.panels.length; k++) {
                    if (PanelsSwapper.panels[k].handlable) {
                        PanelsSwapper.select_panel(PanelsSwapper.panels[k]);
                        break;
                    }
                }
            }
        }), // update_panels_order
        init: (function PanelsSwapper__init () {
            PanelsSwapper.panels = PanelsSwapper.find_panels();
            if (PanelsSwapper.panels.length) {
                for (var i = 0; i < PanelsSwapper.panels.length; i++) {
                    PanelsSwapper.panels[i].index = i;
                    if (PanelsSwapper.panels[i].handlable) {
                        if (!PanelsSwapper.current_panel) {
                            PanelsSwapper.current_panel = PanelsSwapper.panels[i];
                            PanelsSwapper.current_panel.$node.addClass('active-panel');
                        } else {
                            PanelsSwapper.add_handler(PanelsSwapper.panels[i]);
                        }
                    }
                }
                jwerty.key('ctrl+←', Ev.key_decorate(PanelsSwapper.go_prev_panel));
                jwerty.key('ctrl+→', Ev.key_decorate(PanelsSwapper.go_next_panel));
            }
        }) // init

    }; // PanelsSwapper
    PanelsSwapper.init();
    window.PanelsSwapper = PanelsSwapper;

    // select the issue given in the url's hash, or an active one in the html,
    // or the first item of the current list
    if (IssuesList.all.length) {
        (function () {
            IssuesList.all[0].set_current();
            var done = false;

            if (window.location.hash && HistoryManager.re_hash.test(window.location.hash)) {
                var re_result = HistoryManager.re_hash.exec(window.location.hash),
                    issue_id = re_result[2],
                    is_modal = !!re_result[1];
                HistoryManager.add_history(null, issue_id, is_modal, false);
                IssueDetail.open_issue_by_id(issue_id, is_modal);
                done = true;
            } else {
                var $issue_to_select = $(IssuesListIssue.selector + '.active');
                if ($issue_to_select.length) {
                    $issue_to_select.removeClass('active');
                    $issue_to_select[0].IssuesListIssue.set_current(true, true);
                    done = true;
                }
            }
            if (!done) {
                IssuesList.current.go_to_next_item();
            }
        })();
    }

    var activate_quicksearches = (function activate_quicksearches ($inputs) {
        $inputs.each(function() {
            var $input, target, content, content_data, options, qs;
            $input = $(this);
            if (!$input.data('quicksearch')) {
                target = $input.data('target');
                if (!target) { return; }

                options = {
                    bind: 'keyup quicksearch.refresh',
                    removeDiacritics: true,
                    show: function () {
                        this.style.display = "";
                        $(this).removeClass('hidden');
                    },
                    hide: function() {
                        this.style.display = "none";
                        $(this).addClass('hidden');
                    },
                    onBefore: function() {
                        $input.trigger('quicksearch.before');
                    },
                    onAfter: function() {
                        $input.trigger('quicksearch.after');
                    }
                };

                content = $input.data('content');
                if (content) {
                    options.selector = content;
                }
                content_data = $input.data('content-data');
                if (content_data) {
                    options.selector_data = content_data;
                }

                qs = $input.quicksearch(target, options);
                $input.data('quicksearch', qs);

                var clear_input = function(e) {
                    $input.val('');
                    $input.trigger('quicksearch.refresh');
                    $input.focus();
                    return Ev.cancel(e);
                };
                $input.on('keydown', jwerty.event('ctrl+u', clear_input));

                var clear_btn = $input.next('.btn');
                if (clear_btn.length) {
                    clear_btn.on('click', clear_input);
                    clear_btn.on('keyup', jwerty.event('space', clear_input));
                }
            }
        });
    }); // activate_quicksearches
    window.activate_quicksearches = activate_quicksearches;
    activate_quicksearches($('input.quicksearch'));

    if ($().deferrable) {
        $('.deferrable').deferrable();
    }

    var MarkdownManager = {
        re: new RegExp('https?://github.com/([\\w\\-\\.]+/[\\w\\-\\.]+)/(?:issue|pull)s?/(\\d+)'),
        toggle_email_reply: function() {
            var $reply = $(this).parent().next('.email-hidden-reply');
            if (!$reply.hasClass('collapse')) {
                $reply.addClass('collapse').show();
            }
            $reply.collapse('toggle');
            return false;
        }, // toggle_email_reply
        activate_email_reply_toggle: function() {
            $document.on('click', '.email-hidden-toggle a', MarkdownManager.toggle_email_reply);
        }, // activate_email_reply_toggle
        update_link: function(link) {
            link.setAttribute('data-managed', 'true');
            var $link = $(link);
            $link.attr('target', '_blank');
            var matches = link.href.match(MarkdownManager.re);
            // handle link only if current repository
            if (matches) {
                $link.data('repository', matches[1])
                     .data('issue-number', matches[2])
                     .addClass('issue-link hoverable-issue');
            }
        }, // update_link
        update_links: function($nodes) {
            if (!$nodes) {
                $nodes = $('.issue-container');
            }
            $nodes.each(function() {
                var $container = $(this),
                    $base = $container.find('.issue-body, .issue-comment .content');
                $base.find('a:not([data-managed])').each(function() {
                    MarkdownManager.update_link(this);
                });
                $base.find('.issue-link:not(.hoverable-issue)').addClass('hoverable-issue');
            });
        }, // update_links
        find_issue_ident_data: function($link) {
            var data = $link.data();
            if (data.issueNumber && data.repository) {
                return data;
            }
            var parents = $link.parents();
            for (var i = 0; i < parents.length; i++) {
                data = $(parents[i]).data();
                if (data.issueNumber && data.repository) {
                    return data;
                }
            }
            return null;
        }, // find_issue_ident
        handle_issue_link: function(ev) {
            var $link = $(this),
                issue_ident_data = MarkdownManager.find_issue_ident_data($link),
                issue_ident;
            if (!issue_ident_data) { return; }
            issue_ident = {
                number: issue_ident_data.issueNumber,
                id: issue_ident_data.issueId,
                repository: issue_ident_data.repository,
                repository_id: issue_ident_data.repositoryId
            };
            if (!issue_ident.repository || !issue_ident.number) { return; }
            Ev.cancel(ev);
            IssuesListIssue.open_issue(issue_ident, true);
            return false;
        }, // handle_issue_link
        handle_issue_links: function() {
            $document.on('click', 'a.issue-link:not(.issue-item-link)', MarkdownManager.handle_issue_link);
        }, // handle_issue_links
        init: function() {
            MarkdownManager.activate_email_reply_toggle();
            MarkdownManager.update_links();
            MarkdownManager.handle_issue_links();
        } // init
    }; // MarkdownManager
    MarkdownManager.init();


    var MessagesManager = {

        selector: '#messages',
        $node: null,
        template: '<li class="%(classes)s"><button type="button" class="close" title="Close" data-dismiss="alert">×</button>%(content)s</li>',

        extract: (function MessagesManager__extract (html) {
            // Will extract message from ajax requests to put them
            // on the main messages container
            var $fake_node = $('<div />');
            $fake_node.html(html);
            var $new_messages = $fake_node.find(MessagesManager.selector);
            if ($new_messages.length) {
                $new_messages.remove();
                MessagesManager.add_messages($new_messages.children().map(function() { return this.outerHTML; }).toArray());
                return $fake_node.html();
            } else {
                return html;
            }
        }), // extract

        make_message: (function MessagesManager__make_message (content, type) {
            if (typeof content != 'string') {
                content = (content.jquery ? content[0] : content).outerHTML;
            }
            var classes = 'alert' + (type ? ' alert-' + type : '');
            return MessagesManager.template.replace('%(classes)s', classes).replace('%(content)s', content);
        }), // make_messages

        add_messages: (function MessagesManager__add_messages (messages) {
            var html = MessagesManager.$node.html().trim(),
                unique_messages = $.grep(messages, function(message, index) {
                    if (!message) { return false; }
                    if (html && html.indexOf(message) !== -1) {
                        // The message is already displayed, so we skip it
                        return false;
                    }
                    if (messages.indexOf(message, index+1) !== -1) {
                        // the message is available at least one more time in the list, we skip it
                        return false;
                    }
                    // unique_message, we keep it
                    return true;
                });
            if (unique_messages.length) {
                MessagesManager.$node.append(unique_messages);
                MessagesManager.init_auto_hide();
            }
        }), // add_messages

        get_messages: (function MessagesManager__get_alerts () {
            return MessagesManager.$node.children('li.alert');
        }), // get_alerts

        hide_delays: {
            1: 4000,
            2: 2000,
            3: 1500,
            4: 1250,
            'others': 1000
        },

        hide_delay: (function MessagesManager__hide_delay () {
            var count = MessagesManager.get_messages().length;
            return MessagesManager.hide_delays[count] || MessagesManager.hide_delays.others;
        }), // count_messages

        auto_hide_timer: null,
        init_auto_hide: (function MessagesManager__init_auto_hide () {
            if (MessagesManager.auto_hide_timer) {
                clearTimeout(MessagesManager.auto_hide_timer);
                MessagesManager.auto_hide_timer = null;
            }
            var $first = MessagesManager.get_messages().first();
            if (!$first.length) { return; }
            MessagesManager.auto_hide_timer = setTimeout(MessagesManager.auto_hide_first, MessagesManager.hide_delay());
        }), // init_auto_hide

        auto_hide_first: (function MessagesManager__auto_hide_first () {
            MessagesManager.get_messages().first().fadeOut('slow', MessagesManager.remove_first);
        }), // auto_hide_first

        remove_first: (function MessagesManager__remove_first () {
            $(this).remove();
            MessagesManager.auto_hide_timer = null;
            MessagesManager.init_auto_hide();
        }), // remove_first

        init: (function MessagesManager__init () {
            MessagesManager.$node = $(MessagesManager.selector);
            MessagesManager.init_auto_hide();
        }) // init

    }; // MessagesManager

    $.ajaxSetup({
        converters: {
            "text html": MessagesManager.extract
        } // converts
    }); // ajaxSetup
    MessagesManager.init();
    window.MessagesManager = MessagesManager;

    var FormTools = {
        disable_form: (function FormTools__disable_form ($form) {
            // disabled input will be ignored by serialize, so just set them
            // readonly
            $form.find(':input').prop('readonly', true);
            $form.find(':button').prop('disabled', true);
            if (typeof $().select2 != 'undefined') {
                $form.find('select.select2-offscreen').select2('readonly', true);
            }
            $form.data('disabled', true);
        }), // disable_form

        enable_form: (function FormTools__enable_form ($form) {
            $form.find(':input').prop('readonly', false);
            $form.find(':button').prop('disabled', false);
            if (typeof $().select2 != 'undefined') {
                $form.find('select.select2-offscreen').select2('readonly', false);
            }
            $form.data('disabled', false);
        }), // enable_form

        focus_form: (function FormTools__focus_form ($form, delay) {
            if (delay) {
                setTimeout(function() { FormTools.focus_form($form); }, delay)
            } else {
                $form.find(':input:visible:not([type=submit])').first().focus();
            }
        }), // focus_form

        move_cursor_at_the_end: (function FormTools__move_cursor_at_the_end ($input) {
            $input.val($input.val());
        }), // move_cursor_at_the_end

        load_select2: (function FormTools__load_select2 (callback) {
            if (typeof $().select2 == 'undefined') {
                var count_done = 0,
                    on_one_done = function() {
                        count_done++;
                        if (count_done == 2) {
                            callback();
                        }
                    };
                $.ajax({
                    url: window.select2_statics.css,
                    dataType: 'text',
                    cache: true,
                    success: function(data) {
                        $('<style>').attr('type', 'text/css').text(data).appendTo('head');
                        on_one_done();
                    }
                });
                $.ajax({
                    url: window.select2_statics.js,
                    dataType: 'script',
                    cache: true,
                    success: on_one_done
                });
            } else {
                callback();
            }
        }), // load_select2

        select2_matcher: (function FormTools__select2_matcher (term, text) {
                var last = -1;
                term = term.toLowerCase();
                text = text.toLowerCase();
                for (var i = 0; i < term.length; i++) {
                    last = text.indexOf(term[i], last+1);
                    if (last == -1) { return false; }
                }
                return true;
        }), // select2_matcher

        select2_auto_open: (function FormTools__select2_auto_open ($select) {
            // http://stackoverflow.com/a/22210140
            $select.one('select2-focus', FormTools.on_select2_focus)
                   .on("select2-blur", function () {
                        $(this).one('select2-focus', FormTools.on_select2_focus)
                    });
        }), // select2_auto_open

        on_select2_focus: (function FormTools__on_select2_focus () {
           var select2 = $(this).data('select2');
            setTimeout(function() {
                if (!select2.opened()) {
                    select2.open();
                }
            }, 0);
        }), // on_select2_focus

        on_textarea_focus: (function FormTools__on_textarea_focus () {
            $(this).addClass('focused');
        }), // on_textarea_focus

        post_form_with_uuid: (function FormTools__post_form_with_uuid($form, context, on_done, on_failed, data, action) {
            if (typeof data == 'undefined') { data = $form.serializeArray(); }
            if (typeof action == 'undefined') { action = $form.attr('action'); }
            data.push({name:'front_uuid', value: context.uuid});
            $.post(action, data)
                .done($.proxy(on_done, context))
                .fail($.proxy(on_failed, context))
                .always(function() {UUID.set_state(context.uuid, '');});
        }), // post_form_with_uuid

        get_form_context_with_uuid: (function FormTools__get_form_context_with_uuid ($form, front_uuid) {
            if (front_uuid) {
                UUID.set_state(front_uuid, 'waiting');
            } else {
                front_uuid = UUID.generate('waiting');
            }
            return {
                $form: $form,
                uuid: front_uuid
            };
        }), // get_form_context_with_uuid

        handle_form: (function FormTools__handle_form ($form, ev, front_uuid, disable_form_function) {
            Ev.cancel(ev);
            if ($form.data('disabled')) { return false; }
            (disable_form_function || FormTools.disable_form)($form);
            var context = FormTools.get_form_context_with_uuid($form, front_uuid),
                $alert = $form.find('.alert');
            $form.find('button').addClass('loading');
            if ($alert.length) { $alert.remove(); }
            return context;
        }) // handle_form
    };
    window.FormTools = FormTools;

    var IssueEditor = {

        display_issue: (function IssueEditor__display_issue (html, context, force_popup) {
            var is_popup = force_popup || context.$node.parents('.modal').length > 0,
                container = IssueDetail.get_container(is_popup);
            IssueDetail.set_container_loading(container);
            IssueDetail.display_issue(html, context.issue_ident, is_popup);
        }), // display_issue

        handle_form: (function IssueEditor__handle_form ($form, ev) {
            var context = FormTools.handle_form($form, ev);
            if (context === false) { return false; }
            var $node = $form.closest('.issue-container');
            context.issue_ident = IssueDetail.get_issue_ident($node);
            context.$node = $node;
            return context;
        }), // handle_form

        /* CHANGE ISSUE STATE */
        on_state_submit: (function IssueEditor__on_state_submit (ev) {
            var $form = $(this),
                context = IssueEditor.handle_form($form, ev);
            if (context === false) { return false; }

            FormTools.post_form_with_uuid($form, context,
                IssueEditor.on_state_submit_done,
                IssueEditor.on_state_submit_failed
            );
        }), // on_state_submit

        on_state_submit_done: (function IssueEditor__on_state_submit_done (data) {
            this.$form.find('button').removeClass('loading');
            if (data.trim()) {
                IssueEditor.display_issue(data, this);
            } else {
                FormTools.enable_form(this.$form);
                this.$form.find('button.loading').removeClass('loading');
            }
        }), // on_state_submit_done

        on_state_submit_failed: (function IssueEditor__on_state_submit_failed () {
            FormTools.enable_form(this.$form);
            this.$form.find('button').removeClass('loading');
            alert('A problem prevented us to do your action !');
        }), // on_state_submit_failed

        /* POST COMMENT */
        on_comment_submit: (function IssueEditor__on_comment_submit (ev) {
            var $form = $(this),
                context = IssueEditor.handle_form($form, ev),
                text_expected = true,
                handle_pr_review = false,
                action, data;  // both will be set only if review action, else will be default, managed by post_form_with_uuid

            if (context === false) { return false; }

            context['with-pr-review-buttons']  = $form.data('with-pr-review-buttons');

            if (document.activeElement && document.activeElement.name == 'pr-review') {
                handle_pr_review = document.activeElement.value;
                if (handle_pr_review == 'APPROVED') {
                    text_expected = false;
                }
            }

            var $textarea = $form.find('textarea');

            if (text_expected && $textarea.length && !$textarea.val().trim()) {
                $textarea.after('<div class="alert alert-error">You must enter a comment</div>');
                $form.find('button').removeClass('loading');
                FormTools.enable_form($form);
                $textarea.focus();
                return false;
            }

            $form.closest('li.issue-comment')[0].setAttribute('data-front-uuid', context.uuid);

            if (handle_pr_review) {
                // specific action
                action = $form.data('pr-review-url');
                // and specific data: we add the type
                data = $form.serializeArray();
                data.push({name:'state', value: handle_pr_review});
            }

            FormTools.post_form_with_uuid($form, context,
                IssueEditor.on_comment_submit_done,
                IssueEditor.on_comment_submit_failed,
                data, action
            );
        }), // on_comment_submit

        on_comment_submit_done: (function IssueEditor__on_comment_submit_done (data) {
            var $node = $('li.issue-comment[data-front-uuid=' + this.uuid + ']');
            if ($node.length) {
                var $data = $(data);
                if ($data.filter('.comment-create-placeholder').length) {
                    // Remove the existing placeholder if we have a new one
                    $node.prev('.comment-create-placeholder').remove();
                }
                $node.replaceWith($data);
            }
        }), // on_comment_submit_done

        on_comment_submit_failed: (function IssueEditor__on_comment_submit_failed () {
            FormTools.enable_form(this.$form);
            this.$form.find('.alert').remove();
            var $textarea = this.$form.find('textarea');
            $textarea.after('<div class="alert alert-error">We were unable to post this comment</div>');
            this.$form.find('button').removeClass('loading');
            $textarea.focus();
        }), // on_comment_submit_failed

        on_comment_edit_click: (function IssueEditor__on_comment_edit_click () {
            var $link = $(this),
                $comment_node = $link.closest('li.issue-comment');
            if ($link.parent().hasClass('disabled')) { return false; }
            IssueEditor.disable_comment($comment_node, $link);
            $.get($link.attr('href'))
                .done($.proxy(IssueEditor.on_comment_edit_or_delete_loaded, {$comment_node: $comment_node}))
                .fail($.proxy(IssueEditor.on_comment_edit_or_delete_load_failed, {$comment_node: $comment_node, text: 'edit'}));
            return false;
        }), // on_comment_edit_click

        on_comment_delete_click: (function IssueEditor__on_comment_delete_click () {
            var $link = $(this),
                $comment_node = $link.closest('li.issue-comment');
            if ($link.parent().hasClass('disabled')) { return false; }
            IssueEditor.disable_comment($comment_node, $link);
            $.get($link.attr('href'))
                .done($.proxy(IssueEditor.on_comment_edit_or_delete_loaded, {$comment_node: $comment_node}))
                .fail($.proxy(IssueEditor.on_comment_edit_or_delete_load_failed, {$comment_node: $comment_node, text: 'delete confirmation'}));
            return false;
        }), // on_comment_delete_click

        disable_comment: (function IssueEditor__disable_comment ($comment_node, $link) {
            $link.addClass('loading');
            $comment_node.find('.dropdown-menu li').addClass('disabled');
        }), // disable_comment

        on_comment_edit_or_delete_loaded: (function IssueEditor__on_comment_edit_or_delete_loaded (data) {
            this.$comment_node.replaceWith(data);
        }), // on_comment_edit_or_delete_loaded

        on_comment_edit_or_delete_load_failed: (function IssueEditor__on_comment_edit_or_delete_load_failed () {
            this.$comment_node.find('.dropdown-menu li.disabled').removeClass('disabled');
            this.$comment_node.find('a.btn-loading.loading').removeClass('loading');
            alert('Unable to load the ' + this.text + ' form!')
        }), // on_comment_edit_or_delete_load_failed

        // CREATE THE PR-COMMENT FORM
        on_comment_create_placeholder_click: (function IssueEditor__on_comment_create_placeholder_click () {
            var $placeholder = $(this).parent(),
                $comment_box = IssueEditor.create_comment_form_from_template($placeholder, $placeholder.closest('.issue-container'));
            $comment_box.$form.prepend('<input type="hidden" name="entry_point_id" value="' + $placeholder.data('entry-point-id') + '"/>');
            $placeholder.after($comment_box.$node);
            $placeholder.hide();
            $comment_box.$textarea.focus();
        }), // on_comment_create_placeholder_click

        create_comment_form_from_template: (function IssueEditor__create_comment_form_from_template ($trigger, $issue, is_last_pr_comment) {
            var $template = $issue.find('.comment-create-container').first(),
                $node = $template.clone(),
                $form = $node.find('form'),
                $tab_pane = $trigger.closest('.tab-pane'),
                is_commit = $tab_pane.hasClass('commit-files'),
                action = is_commit ? $tab_pane.data('comment-url') : $form.data('pr-url'),
                $textarea;
            if (!is_last_pr_comment) {
                $node.find('button[name=pr-review]').remove();
            }
            $node.removeClass('comment-create-container');
            $form.attr('action', action);
            $textarea = $form.find('textarea');
            $textarea.val('');
            return {$node: $node, $form: $form, $textarea: $textarea};
        }), // create_comment_form_from_template

        // CREATE A NEW ENTRY POINT
        on_new_entry_point_click: (function IssueEditor__on_new_entry_point_click () {
            var $tr = $(this).closest('tr'),
                $tr_comments = $tr.next('.diff-comments'),
                $textarea, $table, $issue, $comment_box;

            // check if already an entry-point
            if ($tr_comments.length) {
                // check if we already have a textarea
                $textarea = $tr_comments.find('textarea');
                if ($textarea.length) {
                    $textarea.focus();
                } else {
                    // no textarea, click on the button to create one
                    $tr_comments.find('.comment-create-placeholder button').click();
                }
                return false;
            }

            // we need to create an entry point
            $table = $tr.closest('table');
            $issue = $table.closest('.issue-container');
            path = $table.data('path');
            sha = $table.data('sha');
            position = $tr.data('position');

            // create a tr for the entry-point
            $tr_comments = $issue.find('.code-comments-template tr.diff-comments').clone();
            $comment_box = IssueEditor.create_comment_form_from_template($table, $issue);
            $comment_box.$form.prepend('<input type="hidden" name="path" value="' + path + '"/>' +
                                       '<input type="hidden" name="sha" value="' + sha + '"/>' +
                                       '<input type="hidden" name="position" value="' + position + '"/>');
            $tr_comments.find('ul').append($comment_box.$node);
            $tr.after($tr_comments);
            $comment_box.$textarea.focus();

        }), // on_new_entry_point_click

        // CANCEL/DELETE COMMENTS
        remove_comment: (function IssueEditor__remove_comment ($li) {

            // if many ones
            if ($li.length > 1) {
                $li.each(function() {
                    IssueEditor.remove_comment($(this));
                });
                return;
            }

            var $form = $li.find('form'),
                removed = false,
                $placeholder = $li.prev('.comment-create-placeholder'),
                $tr_comments = $li.closest('tr.diff-comments');

            FormTools.disable_form($form);

            // it's a non submitted answer to a previous PR comment
            if ($placeholder.length) {
                $li.remove();
                removed = true;
            }

            // it's in a pr entry point
            if ($tr_comments.length) {
                if (!removed) {
                    $li.remove();
                    removed = true;
                }
                // Do we have other comments
                if (!$tr_comments.find('.issue-comment').length) {
                    // If no we can remove the entry point
                    $tr_comments.remove();
                    return false;
                }
            }

            if ($placeholder.length && removed) {
                $placeholder.show();
                return false;
            }

            // It's a template !
            if ($li.hasClass('comment-create-container')) {
                $li.find('textarea').val('');
                FormTools.enable_form($form);
                return false;
            }

            // other case, simply delete the comment
            $li.remove()

        }), // remove_comment

        on_comment_create_cancel_click: (function IssueEditor__on_comment_create_cancel_click () {
            IssueEditor.remove_comment($(this).closest('li.issue-comment'));
        }), //on_comment_create_cancel_click

        on_comment_edit_or_delete_cancel_click: (function IssueEditor__on_comment_edit_or_delete_cancel_click () {
            var $note = $(this).closest('li.issue-comment');

            FormTools.disable_form($note.find('form'));

            $.get($note.data('url'))
                .done(function(data) {
                    $note.replaceWith(data);
                })
                .fail(function() {
                    alert('Unable to retrieve the original comment')
                });
        }), // on_comment_edit_or_delete_cancel_click

        // EDIT ISSUES FIELDS, ONE BY ONE
        on_issue_edit_field_click: (function IssueEditor__on_issue_edit_field_click () {
            var $link = $(this);
            if ($link.hasClass('loading')) { return false; }
            $link.addClass('loading');
            $.ajax({
                url: $link.attr('href'),
                type: 'GET',
                success: IssueEditor.on_issue_edit_field_ready,
                error: IssueEditor.on_issue_edit_field_failed,
                context: $link
            });
            return false;
        }), // on_issue_edit_field_click

        on_issue_edit_field_failed: (function IssueEditor__on_issue_edit_field_failed (xhr, data) {
            if (xhr.status == 409) {
                // 409 Conflict Indicates that the request could not be processed because of
                // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                return $.proxy(IssueEditor.on_issue_edit_field_ready, this)(data);
            }
            var $link = this;
            $link.removeClass('loading');
             alert('A problem prevented us to do your action !');
        }), // on_issue_edit_field_failed

        on_issue_edit_field_ready: (function IssueEditor__on_issue_edit_field_ready (data) {
            var $link = this;
            if (!data.trim() || data == 'error') {  // error if 409 from on_issue_edit_field_failed
                $link.removeClass('loading');
                return false;
            }
            var field = $link.data('field'), $form,
                $placeholder = $link.closest('.issue-content').find('.edit-place[data-field=' + field + ']'),
                method = 'issue_edit_' + field + '_insert_field_form';
            if (typeof IssueEditor[method] == 'undefined') {
                method = 'issue_edit_default_insert_field_form';
            }
            $form = IssueEditor[method]($link, $placeholder, data);
            method = 'issue_edit_' + field + '_field_prepare';
            if (typeof IssueEditor[method] != 'undefined') {
                IssueEditor[method]($form);
            }
        }), // on_issue_edit_field_ready

        issue_edit_default_insert_field_form: (function IssueEditor__issue_edit_default_insert_field_form ($link, $placeholder, data) {
            var $form = $(data);
            $link.remove();
            $placeholder.replaceWith($form);
            FormTools.focus_form($form, 50);
            return $form;
        }), // issue_edit_default_insert_field_form

        issue_edit_title_insert_field_form: (function IssueEditor__issue_edit_title_insert_field_form ($link, $placeholder, data) {
            var left = $placeholder.position().left, $form;
            $placeholder.parent().after($placeholder);
            $form = IssueEditor.issue_edit_default_insert_field_form($link, $placeholder, data);
            $form.css('left', left + 'px');
            return $form;
        }), // issue_edit_title_insert_field_form

        issue_edit_milestone_field_prepare: (function IssueEditor__issue_edit_milestone_field_prepare ($form, dont_load_select2) {
            var $select = $form.find('#id_milestone');
            if (!$select.length) { return; }
            var callback = function() {
                var milestones_data = $select.data('milestones'),
                    format = function(state, include_title) {
                        if (state.children) {
                            return state.text.charAt(0).toUpperCase() + state.text.substring(1) + ' milestones';
                        }
                        var data = milestones_data[state.id];
                        if (data) {
                            var result = '<i class="fa fa-tasks text-' + data.state + '"> </i> <strong>' + (data.title.length > 25 ? data.title.substring(0, 20) + '…' : data.title);
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
                    };
                $select.select2({
                    formatSelection: function(state) { return format(state, false); },
                    formatResult:  function(state) { return format(state, true); },
                    escapeMarkup: function(m) { return m; },
                    dropdownCssClass: 'select2-milestone',
                    matcher: FormTools.select2_matcher
                });
                FormTools.select2_auto_open($select);
                $form.closest('.modal').removeAttr('tabindex');  // tabindex set to -1 bugs select2
            };
            if (dont_load_select2) {
                callback();
            } else {
                FormTools.load_select2(callback);
            }
        }), // issue_edit_milestone_field_prepare

        issue_edit_assignees_field_prepare: (function IssueEditor__issue_edit_assignees_field_prepare ($form, dont_load_select2) {
            var $select = $form.find('#id_assignees');
            if (!$select.length) { return; }
            var callback = function() {
                var collaborators_data = $select.data('collaborators'),
                    format = function(state, include_icon) {
                        var data = collaborators_data[state.id],
                            result;
                        if (data) {
                            var avatar_url = data.full_avatar_url;
                            if (avatar_url.indexOf('?') == -1) { avatar_url += '&s=24' } else { avatar_url += '?s=24'; }
                            result = '<img class="avatar-tiny img-circle" src="' + avatar_url + '" /> <strong>' + (data.username.length > 25 ? data.username.substring(0, 20) + '…' : data.username);
                        } else {
                            result = 'No one assigned';
                        }
                        if (include_icon) {
                            result = '<i class="fa fa-hand-o-right"> </i> ' + result;
                        }
                        return result;
                    },
                    formatNoMatches = function(term) {
                        return term ? "No matches found" : "No more available user";
                    };
                $select.select2({
                    formatSelection: function(state) { return format(state, true); },
                    formatResult:  function(state) { return format(state, false); },
                    formatNoMatches: formatNoMatches,
                    escapeMarkup: function(m) { return m; },
                    dropdownCssClass: 'select2-assignees',
                    matcher: FormTools.select2_matcher
                });
                FormTools.select2_auto_open($select);
                $form.closest('.modal').removeAttr('tabindex');  // tabindex set to -1 bugs select2
            };
            if (dont_load_select2) {
                callback();
            } else {
                FormTools.load_select2(callback);
            }
        }), // issue_edit_assignees_field_prepare

        issue_edit_labels_field_prepare: (function IssueEditor__issue_edit_labels_field_prepare ($form, dont_load_select2) {
            var $select = $form.find('#id_labels');
            if (!$select.length) { return; }
            var callback = function() {
                var labels_data = $select.data('labels'),
                    format = function(state, include_type) {
                        if (state.children) {
                            return state.text;
                        }
                        var data = labels_data[state.id];
                        var result = data.typed_name;
                        if (include_type && data.type) {
                            result = '<strong>' + data.type + ':</strong> ' + result;
                        }
                        return '<span style="border-bottom-color: #' + data.color + '">' + result + '</span>';
                    },
                    matcher = function(term, text, opt) {
                        return FormTools.select2_matcher(term, labels_data[opt.val()].search);
                    },
                    formatNoMatches = function(term) {
                        return term ? "No matches found" : "No more available labels";
                    };
                $select.select2({
                    formatSelection: function(state) { return format(state, true); },
                    formatResult:  function(state) { return format(state, false); },
                    formatNoMatches: formatNoMatches,
                    escapeMarkup: function(m) { return m; },
                    dropdownCssClass: 'select2-labels',
                    matcher: matcher,
                    closeOnSelect: false
                });
                FormTools.select2_auto_open($select);
                $form.closest('.modal').removeAttr('tabindex');  // tabindex set to -1 bugs select2
            };
            if (dont_load_select2) {
                callback();
            } else {
                FormTools.load_select2(callback);
            }
        }), // issue_edit_labels_field_prepare

        issue_edit_projects_field_prepare: (function IssueEditor__issue_edit_projects_field_prepare ($form, dont_load_select2) {
            var $select = $form.find('#id_columns');
            if (!$select.length) { return; }
            var callback = function() {
                var columns_data = $select.data('columns'),
                    selected_projects = {},
                    updateSelectedProjects = function(vals) {
                        selected_projects = {};
                        if (!$.isArray(vals)) { return; }
                        for (var i=0; i<vals.length; i++) {
                            selected_projects[columns_data[vals[i]].project_number] = true;
                        }
                    },
                    format = function(state, include_project) {
                        if (state.children) {
                            return state.text;
                        }
                        var data = columns_data[state.id];
                        var result = data.name;
                        if (include_project) {
                            result = '<strong>' + data.project_name + ':</strong> ' + result;
                        }
                        return '<span>' + result + '</span>';
                    },
                    matcher = function(term, text, opt) {
                        var column_id = opt.val();
                        if (column_id && selected_projects[columns_data[column_id].project_number]) {
                            return false;
                        }
                        return FormTools.select2_matcher(term, columns_data[column_id].search);
                    },
                    formatNoMatches = function(term) {
                        return term ? "No matches found" : "No more available projects";
                    },
                    onChange = function(e) {
                        if (e.val) {
                            updateSelectedProjects(e.val);
                        }
                        // will hide columns choices from already selected projects
                        $select.data('select2').updateResults();
                    },
                    onSelecting = function(e) {
                        if (e.val && selected_projects[columns_data[e.val].project_number]) {
                            e.preventDefault();
                        }
                    };

                updateSelectedProjects($select.val());

                $select.select2({
                    formatSelection: function(state) { return format(state, true); },
                    formatResult:  function(state) { return format(state, false); },
                    formatNoMatches: formatNoMatches,
                    escapeMarkup: function(m) { return m; },
                    dropdownCssClass: 'select2-projects',
                    matcher: matcher,
                    closeOnSelect: false
                }).on('change', onChange)
                  .on('select2-selecting', onSelecting);
                FormTools.select2_auto_open($select);
                $form.closest('.modal').removeAttr('tabindex');  // tabindex set to -1 bugs select2
            };
            if (dont_load_select2) {
                callback();
            } else {
                FormTools.load_select2(callback);
            }

        }), // issue_edit_projects_field_prepare

        on_issue_edit_field_cancel_click: (function IssueEditor__on_issue_edit_field_cancel_click () {
            var $btn = $(this),
                $form = $btn.closest('form');
            if ($form.data('disabled')) { return false; }
            FormTools.disable_form($form);
            $btn.addClass('loading');
            var $container = $form.closest('.issue-container'),
                issue_ident = IssueDetail.get_issue_ident($container),
                is_popup = IssueDetail.is_modal($container);
            IssuesListIssue.open_issue(issue_ident, is_popup, true, true);
            if (is_popup) {
                $container.closest('.modal').attr('tabindex', '-1');
            }
            return false;
        }), // on_issue_edit_field_cancel_click

        on_issue_edit_field_submit: (function IssueEditor__on_issue_edit_field_submit (ev) {
            var $form = $(this),
                context = IssueEditor.handle_form($form, ev);
            if (context === false) { return false; }

            FormTools.post_form_with_uuid($form, context,
                IssueEditor.on_issue_edit_submit_done,
                IssueEditor.on_issue_edit_submit_fail
            );
            return false;
        }), // on_issue_edit_field_submit

        on_issue_edit_submit_done: (function IssueEditor__on_issue_edit_submit_done (data) {
            this.$form.find('button.loading').removeClass('loading');
            if (data.trim() || data == 'error') {  // error if 409 from on_issue_edit_submit_fail
                IssueEditor.display_issue(data, this);
            } else {
                FormTools.enable_form(this.$form);
                this.$form.find('button.loading').removeClass('loading');
                FormTools.focus_form(this.$form);
            }
        }), // on_issue_edit_submit_done

        on_issue_edit_submit_fail: (function IssueEditor__on_issue_edit_submit_fail (xhr, data) {
            if (xhr.status == 409) {
                // 409 Conflict Indicates that the request could not be processed because of
                // conflict in the request, such as an edit conflict between multiple simultaneous updates.
                return $.proxy(IssueEditor.on_issue_edit_submit_done, this)(data);
            }
            FormTools.enable_form(this.$form);
            this.$form.find('button.loading').removeClass('loading');
            alert('A problem prevented us to do your action !');
        }), // on_issue_edit_submit_fail

        // UPDATE COMMENTS FROM WEBSOCKET
        on_update_alert: (function IssueEditor__on_update_alert (topic, args, kwargs) {
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid) && UUID.has_state(kwargs.front_uuid, 'waiting')) {
                setTimeout(function() {
                    IssueEditor.on_update_alert(topic, args, kwargs);
                }, 100);
                return;
            }
            // Replace "waiting" comments
            if (kwargs.url && (kwargs.model == 'IssueComment' || kwargs.model == 'CommitComment' || kwargs.model == 'PullRequestComment' || kwargs.model == 'PullRequestReview')) {

                var selector = 'li.issue-comment[data-model=' + kwargs.model + '][data-id=' + kwargs.id + ']';
                if (kwargs.front_uuid) {
                    selector += ', li.issue-comment[data-front-uuid=' + kwargs.front_uuid + ']';
                }
                var $nodes = $(selector);
                if ($nodes.length) {
                    $.get(kwargs.url).done(function(data) {
                        $nodes.replaceWith(data);
                        MarkdownManager.update_links($nodes);
                    });
                }
            }
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                UUID.set_state(kwargs.front_uuid, '');
            }
        }), // on_update_alert

        on_delete_alert: (function IssueEditor__on_delete_alert (topic, args, kwargs) {
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid) && UUID.has_state(kwargs.front_uuid, 'waiting')) {
                setTimeout(function() {
                    IssueEditor.on_update_alert(topic, args, kwargs);
                }, 100);
                return;
            }
            // Remove "waiting deletion" comments
            if (kwargs.model == 'IssueComment' || kwargs.model == 'CommitComment' || kwargs.model == 'PullRequestComment') {

                var selector = 'li.issue-comment[data-model=' + kwargs.model + '][data-id=' + kwargs.id + ']';
                if (kwargs.front_uuid) {
                    selector += ', li.issue-comment[data-front-uuid=' + kwargs.front_uuid + ']';
                }
                var $nodes = $(selector);
                if ($nodes.length) {
                    IssueEditor.remove_comment($nodes);
                }
            }
            if (kwargs.front_uuid && UUID.exists(kwargs.front_uuid)) {
                UUID.set_state(kwargs.front_uuid, '');
            }
        }), // on_delete_alert

        // CREATE ISSUE
        create: {
            allowed_path_re: new RegExp('^/([\\w\\-\\.]+/[\\w\\-\\.]+)/(?:issues/|dashboard/|board/)'),
            $modal: null,
            $modal_body: null,
            $modal_footer: null,
            $modal_submit: null,
            $modal_repository_placeholder: null,
            modal_issue_body: '<div class="modal-body"><div class="issue-container"></div></div>',
            url: $body.data('create-issue-url'),

            get_form: function() {
                return $('#issue-create-form');
            },

            start: (function IssueEditor_create__start () {
                if (!window.location.pathname.match(IssueEditor.create.allowed_path_re)) {
                    return;
                }
                if ($('#milestone-edit-form').is(':visible')) {
                    return;
                }
                if (IssueEditor.create.$modal.is(':visible')) {
                    return;
                }
                IssueEditor.create.$modal_repository_placeholder.text(main_repository);
                IssueEditor.create.$modal_footer.hide();
                IssueEditor.create.$modal_body.html('<p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p>');
                IssueEditor.create.$modal_submit.removeClass('loading');
                $body.append(IssueEditor.create.$modal); // move at the end to manage zindex
                IssueEditor.create.$modal.modal('show');
                $.get(IssueEditor.create.url)
                    .done(IssueEditor.create.on_load_done)
                    .fail(IssueEditor.create.on_load_failed);
                IssueEditor.create.$modal_footer.find('.alert').remove();
                return false;
            }), // start

            on_load_done: (function IssueEditor_create__on_load_done (data) {
                IssueEditor.create.$modal_body.html(data);
                var $form = IssueEditor.create.get_form();
                IssueEditor.create.update_form($form);
                FormTools.focus_form($form, 250);
                IssueEditor.create.$modal_footer.show();
            }), // on_load_done

            on_load_failed: (function() {
                IssueEditor.create.$modal_body.html('<div class="alert alert-error">A problem prevented us to display the form</div>');
            }), // on_load_failed

            update_form: (function IssueEditor_create__update_form ($form) {
                var select2_callback = function() {
                    IssueEditor.issue_edit_milestone_field_prepare($form, true);
                    IssueEditor.issue_edit_assignees_field_prepare($form, true);
                    IssueEditor.issue_edit_labels_field_prepare($form, true);
                    IssueEditor.issue_edit_projects_field_prepare($form, true);
                };
                FormTools.load_select2(select2_callback);
            }), // update_form

            on_form_submit: (function IssueEditor_create__on_form_submit (ev) {
                Ev.cancel(ev);
                var $form = IssueEditor.create.get_form();
                if ($form.data('disabled')) { return false; }
                FormTools.disable_form($form);
                IssueEditor.create.$modal_submit.addClass('loading');
                IssueEditor.create.$modal_footer.find('.alert').remove();
                var front_uuid = UUID.generate('waiting'), context = {'front_uuid': front_uuid};
                FormTools.post_form_with_uuid($form, context,
                    IssueEditor.create.on_submit_done,
                    IssueEditor.create.on_submit_failed
                );
            }), // on_form_submit

            on_submit_done: (function IssueEditor_create__on_submit_done (data) {
                IssueEditor.create.$modal_body.scrollTop(0);
                if (data.substr(0, 6) == '<form ') {
                    // we have an error, the whole form is returned
                    IssueEditor.create.get_form().replaceWith(data);
                    var $form = IssueEditor.create.get_form();
                    FormTools.enable_form($form);
                    FormTools.focus_form($form, 250);
                    IssueEditor.create.update_form($form);
                    IssueEditor.create.$modal_submit.removeClass('loading');
                } else {
                    // no error, we display the issue
                    IssueEditor.create.display_created_issue(data, this.front_uuid);
                }
            }), // on_submit_done

            on_submit_failed: (function IssueEditor_create__on_submit_failed () {
                var $form = IssueEditor.create.get_form();
                FormTools.enable_form($form);
                FormTools.focus_form($form, 250);
                IssueEditor.create.$modal_submit.removeClass('loading');
                IssueEditor.create.$modal_footer.prepend('<div class="alert alert-error">A problem prevented us to save the issue</div>');
            }), // on_submit_failed

            display_created_issue: (function IssueEditor_create__display_created_issue (html, front_uuid) {
                var $html = $('<div/>').html(html),
                    $content = $html.children('.issue-content'),
                    context = {
                        issue_ident: {
                            repository: $content.data('repository'),
                            repository_id: $content.data('repository-id'),
                            number: $content.data('issue-number') || 'pk-' + $content.data('issue-id'),
                            id: $content.data('issue-id')
                        }
                    },
                    container = IssueDetail.get_container_waiting_for_issue(context.issue_ident, true, true);
                IssueEditor.create.$modal.modal('hide');
                context.$node = container.$node;
                IssueEditor.display_issue($html.children(), context);
                $content.data('front-uuid', front_uuid);
            }), // display_created_issue

            on_created_modal_hidden: (function IssueEditor_create__on_created_modal_hidden () {
                var $modal = $(this);
                setTimeout(function() { $modal.remove(); }, 50);
            }), // on_created_modal_hidden

            init: (function IssueEditor_create__init () {
                IssueEditor.create.$modal = $('#issue-create-modal');
                IssueEditor.create.$modal_repository_placeholder = IssueEditor.create.$modal.find('.modal-header > h6 > span');
                IssueEditor.create.$modal_footer = IssueEditor.create.$modal.children('.modal-footer');
                IssueEditor.create.$modal_body = IssueEditor.create.$modal.children('.modal-body');
                IssueEditor.create.$modal_submit = IssueEditor.create.$modal_footer.find('button.submit');

                jwerty.key('c', Ev.key_decorate(IssueEditor.create.start));
                $('.add-issue-btn a').on('click', Ev.stop_event_decorate(IssueEditor.create.start));
                $document.on('submit', '#issue-create-form', IssueEditor.create.on_form_submit);
                $document.on('click', '#issue-create-modal .modal-footer button.submit', IssueEditor.create.on_form_submit);
                $document.on('hidden.modal', '#modal-issue-created', IssueEditor.create.on_created_modal_hidden);
            }) // IssueEditor_create__init
        },

        init: (function IssueEditor__init () {
            $document.on('submit', '.issue-edit-state-form', IssueEditor.on_state_submit);

            $document.on('click', 'a.issue-edit-btn', Ev.stop_event_decorate(IssueEditor.on_issue_edit_field_click));
            $document.on('click', 'form.issue-edit-field button.btn-cancel', Ev.stop_event_decorate(IssueEditor.on_issue_edit_field_cancel_click));
            $document.on('submit', 'form.issue-edit-field', Ev.stop_event_decorate(IssueEditor.on_issue_edit_field_submit));

            $document.on('click', '.comment-create-placeholder button', IssueEditor.on_comment_create_placeholder_click);

            $document.on('submit', '.comment-form', IssueEditor.on_comment_submit);
            $document.on('focus', '.comment-form textarea', FormTools.on_textarea_focus);

            $document.on('click', '.comment-create-form button[type=button]', IssueEditor.on_comment_create_cancel_click);
            $document.on('click', '.comment-edit-form button[type=button], .comment-delete-form button[type=button]', IssueEditor.on_comment_edit_or_delete_cancel_click);

            $document.on('click', '.comment-edit-btn', Ev.stop_event_decorate(IssueEditor.on_comment_edit_click));
            $document.on('click', '.comment-delete-btn', Ev.stop_event_decorate(IssueEditor.on_comment_delete_click));

            $document.on('click', 'td.code span.btn-comment', IssueEditor.on_new_entry_point_click);

            IssueEditor.create.init();
        }) // init
    }; // IssueEditor
    IssueEditor.init();

    // focus input for repository-switcher
    var $repos_switcher_input = $('#repository-switcher-filter').find('input');
    if ($repos_switcher_input.length) {
        $repos_switcher_input.closest('li').on('click', function(ev) { ev.stopPropagation(); });
        $('#repository-switcher').on('focus', Ev.set_focus($repos_switcher_input, 200))
            .on('focus', function() {
                var $link = $(this);
                $link.next().css('max-height', $(window).height() - $link.offset().top - $link.outerHeight() - 10);
            });
    }
    // auto-hide owner if it has no repo found on quicksearch
    var $repos_switcher_groups = $('#repository-switcher-content').find('li.subscriptions-group');
    $repos_switcher_input.on('quicksearch.after', function() {
        $repos_switcher_groups.each(function() {
            var $group = $(this);
            $group.toggle(!!$group.find('li:not(.hidden)').length);
        });
    });

    var Activity = {
        selectors: {
            main: '.activity-feed',
            issue_link: '.box-section > h3 > a, a.referenced_issue',
            buttons: {
                refresh: '.timeline-refresh',
                more: '.placeholder.more a'
            },
            entries: {
                all: '.chat-box > li',
                first: '.chat-box:first > li:first',
                last: '.chat-box:last > li:last'
            },
            containers: {
                issues: '.box-section',
                repositories: '.activity-repository'
            },
            count_silent: {
                issues: '.box-section.silent',
                repositories: '.activity-repository.silent .box-section'
            },
            find_empty: ':not(:has(.chat-box > li))',
            filter_checkboxes: '.activity-filter input',
            filter_links: '.activity-filter a'
        },

        on_issue_link_click: (function Activity__on_issue_link_click () {
            var $link = $(this),
                $block = $link.data('issue-number') ? $link : $link.closest('.box-section'),
                issue = new IssuesListIssue({}, null);
            issue.set_issue_ident({
                number: $block.data('issue-number'),
                id: $block.data('issue-id'),
                repository: $block.data('repository'),
                repository_id: $block.data('repository-id')
            });
            issue.get_html_and_display($link.attr('href'), true);
            return false;
        }), // on_issue_link_click

        get_main_node: (function Activity__get_main_node ($node) {
            return $node.closest(Activity.selectors.main);
        }), // get_main_node

        get_existing_entries_for_score: (function Activity__get_existing_entries_for_score($pivot, where, score) {
            var result = [], $check = $pivot, $same_score_entries;
            if (!score) { return }
            while (true) {
                $check = $check[where]();
                if (!$check.length) { break; }
                $same_score_entries = $check.find(Activity.selectors.entries.all + '[data-score="' + score + '"]');
                if (!$same_score_entries.length) { break; }
                result = result.concat($same_score_entries.map(function() {return $(this).data('ident'); }).toArray());
            }
            return result;
        }), // get_existing_entries_for_score

        add_loaded_entries: (function Activity__add_loaded_entries($main_node, data, limits, $placeholder, silent, callback) {
            var $container = $('<div />'),
                mode = $main_node.data('mode'),
                idents = {}, $entries, $entry, is_min, is_max, count, score, ident;

            // put data in a temporary container to manage them
            $container.append(data);
            $entries = $container.find(Activity.selectors.entries.all);

            // get idents for existing entries with same min/max scores
            if (limits.min) {
                idents.min = Activity.get_existing_entries_for_score($placeholder, 'next', limits.min);
            }
            if (limits.max) {
                idents.max = Activity.get_existing_entries_for_score($placeholder, 'prev', limits.max);
            }

            // we need numbers to compare
            if (limits.min) { limits.min = parseFloat(limits.min)}
            if (limits.max) { limits.max = parseFloat(limits.max)}

            // remove entries with boundaries already presents
            for (var i = 0; i < $entries.length; i++) {
                $entry = $($entries[i]);
                score = $entry.data('score');
                is_min = (limits.min && score == limits.min);
                is_max = (limits.max && score == limits.max);
                if (is_min || is_max) {
                    ident = $entry.data('ident');
                    if (    is_min && idents.min && $.inArray(ident, idents.min) != -1
                         ||
                            is_max && idents.max && $.inArray(ident, idents.max) != -1
                        ) {
                        $entry.remove();
                    }
                }
            }

            // clean empty nodes
            if (mode == 'issues' || mode == 'repositories') {
                $container.find(Activity.selectors.containers.issues + Activity.selectors.find_empty).remove();
                if (mode == 'repositories') {
                    $container.find(Activity.selectors.containers.repositories + Activity.selectors.find_empty).remove();
                }
            }

            count = $container.find(Activity.selectors.entries.all).length;

            if (!silent) {
                // remove old "recent" marks
                $main_node.find(Activity.selectors.containers[mode] + '.recent:not(.silent)').removeClass('recent');
            }

            // insert data if there is still
            if (count) {
                $entries = $container.children();
                if (silent) {
                    $entries.addClass('silent');
                    $entries.insertAfter($placeholder);
                } else {
                    $entries.replaceAll($placeholder);
                    setTimeout(function() { $entries.addClass('recent'); }, 10);
                }
                if (callback) { callback('ok'); }
            } else {
                if (!silent) {
                    Activity.update_placeholder($placeholder, 'nothing', callback);
                } else {
                    if (callback) { callback('nothing'); }
                }
            }

            Activity.toggle_empty_parts($main_node);

            return count;
        }), // add_loaded_entries

        placeholders: {
            nothing: {
                message: 'Nothing new',
                icon: 'fa fa-eye-slash',
                delay: 1000
            },
            error: {
                message: 'Error while loading',
                icon: 'fa fa-times-circle',
                delay: 3000
            },
            loading: {
                message: 'Loading',
                icon: 'fa fa-spinner fa-spin',
                delay: -1
            },
            more: {
                message: 'Load more',
                icon: 'fa fa-plus',
                delay: -1,
                classes: 'box-footer',
                link: '#'
            },
            missing: {
                message: 'Load missing',
                icon: 'fa fa-plus',
                delay: -1,
                classes: 'more box-footer',
                link: '#'
            },
            new_activity: {
                message: '<span>New activity</span> available, click to see them!',
                icon: 'fa fa-refresh',
                delay: -1,
                classes: 'timeline-refresh',
                link: '#'
            }
        }, // placeholders

        update_placeholder: (function Activity__update_placeholder($placeholder, type, callback, replace_type) {
            var params = Activity.placeholders[type];
            var html = '<i class="' + params.icon + '"> </i> ' + params.message;
            if (params.link) {
                html = '<a href="' + params.link + '">' + html + '</a>';
            }
            $placeholder.html(html);
            $placeholder[0].className = 'placeholder visible ' + type + (params.classes ? ' ' + params.classes : '');  // use className to remove all previous
            if (params.delay != -1) {
                setTimeout(function() {
                    if (replace_type) {
                        Activity.update_placeholder($placeholder, replace_type);
                        if (callback) { callback(type); }
                    } else {
                        $placeholder.removeClass('visible');
                        setTimeout(function() {
                            $placeholder.remove();
                            if (callback) { callback(type); }
                        }, 320);
                    }
                }, params.delay);
            }
        }), // update_placeholder

        load_data: (function Activity__load_data($main_node, limits, $placeholder, silent, callback, retry_placeholder) {
            var data = { partial: 1};

            if (limits.min) { data.min = limits.min; }
            if (limits.max) { data.max = limits.max; }

            $.ajax({
                url: $main_node.data('url'),
                data: data,
                dataType: 'html',
                success: function(data) {
                    Activity.add_loaded_entries($main_node, data, limits, $placeholder, silent, callback);
                },
                error: function() {
                    if (silent) {
                        callback('error');
                    } else {
                        Activity.update_placeholder($placeholder, 'error', callback, retry_placeholder);
                    }
                }
            });

        }), // load_data

        on_refresh_button_click: (function Activity__on_refresh_button_click () {
            var $main_node, $refresh_buttons, mode, $placeholder, $silent_entries;
            $main_node = Activity.get_main_node($(this));

            $refresh_buttons = $main_node.find('.timeline-refresh');

            if ($refresh_buttons.hasClass('disabled')) { return false; }
            $refresh_buttons.addClass('disabled');

            $main_node.children('.box-content').scrollTop(1).scrollTop(0);
            mode = $main_node.data('mode');

            $silent_entries = $main_node.find(Activity.selectors.containers[mode] + '.silent');

            if ($silent_entries.length) {

                $main_node.find('.placeholder.new_activity').remove();
                $main_node.find(Activity.selectors.containers[mode] + '.recent:not(.silent)').removeClass('recent');
                $silent_entries.removeClass('silent').addClass('recent');
                $refresh_buttons.removeClass('disabled');

            } else {

                $placeholder = $('<div class="placeholder loading"><i class="' + Activity.placeholders.loading.icon + '"> </i> ' + Activity.placeholders.loading.message + '</div>');
                $main_node.find(Activity.selectors.containers[mode]).first().before($placeholder);
                setTimeout(function() { $placeholder.addClass('visible'); }, 10);

                Activity.get_fresh_data($main_node, $placeholder, false, function() {
                    $refresh_buttons.removeClass('disabled');
                });
            }

            return false;
        }), // on_refresh_button_click

        display_silent_activity: (function Activity__display_silent_activity() {

        }), // display_silent_activity

        get_fresh_data: (function Activity__get_fresh_data($main_node, $placeholder, silent, callback) {
            var score = $main_node.find(Activity.selectors.entries.first).data('score');
            Activity.load_data($main_node, {min: score}, $placeholder, silent, callback);
        }), // get_fresh_data

        check_new_activity: (function Activity__check_new_activity($main_node) {
            var $placeholder = $('<div class="placeholder silent-checking"></div>'),
                $new_activity_placeholder = $main_node.find('.placeholder.new_activity'),
                mode = $main_node.data('mode');

            $main_node.find(Activity.selectors.containers[mode]).first().before($placeholder);

            Activity.get_fresh_data($main_node, $placeholder, true, function(result_type) {
                if (result_type == 'ok') {
                    if ($new_activity_placeholder.length) {
                        $placeholder.remove();
                    } else {
                        Activity.update_placeholder($placeholder, 'new_activity');
                        $new_activity_placeholder = $placeholder;
                    }
                    var count = $main_node.find(Activity.selectors.count_silent[mode]).length;
                    $new_activity_placeholder.find('span').text(count + ' new entr' + (count > 1 ? 'ies' : 'y'));
                    $new_activity_placeholder.addClass('flash');
                    setTimeout(function() {
                        $new_activity_placeholder.removeClass('flash');
                    }, 1000);
                } else {
                    $placeholder.remove();
                }
            });

        }), // check_new_activity

        delay_check_new_activity: (function Activity__delay_check_new_activity($main_node) {
            if (typeof $main_node.selector == 'undefined') {
                // node is passed as a string when html loaded for the first time
                $main_node = $($main_node);
                if (!$main_node.length) {
                    setTimeout(function() {
                        Activity.delay_check_new_activity($main_node.selector);
                    }, 1000);
                    return;
                }
            }
            setInterval(function() {
                Activity.check_new_activity($main_node);
            }, 30000);
        }), // delay_check_new_activity

        on_more_button_click: (function Activity__on_more_button_click () {
            var $this = $(this), $main_node,
                $placeholder = $this.parent(),
                $previous_entry, $next_entry,
                limits = {},
                is_missing_btn = $placeholder.hasClass('missing');

            if ($this.hasClass('disabled')) { return false; }
            $this.addClass('disabled');

            Activity.update_placeholder($placeholder, 'loading');

            $main_node = Activity.get_main_node($placeholder);

            $previous_entry = $placeholder.prev().find(Activity.selectors.entries.last);
            if ($previous_entry.length) {
                limits.max = $previous_entry.data('score');
            }
            $next_entry = $placeholder.next().find(Activity.selectors.entries.first);
            if ($next_entry.length) {
                limits.min = $next_entry.data('score');
            }

            Activity.load_data($main_node, limits, $placeholder, false, null, is_missing_btn ? 'missing' : 'more');

            return false;
        }), // on_more_button_click

        on_filter_change: (function Activity__on_filter_change () {
            var $checkbox = $(this).closest('a').find('input'),  // works if ev on A or INPUT
                checked = $checkbox.is(':checked'),
                is_all = $checkbox.attr('name') == 'toggle-all',
                $feed = $checkbox.closest('.activity-feed'),
                $checkboxes = null;
            if (is_all) {
                $checkboxes = $feed.find(Activity.selectors.filter_checkboxes + ':not([name=toggle-all])');
            } else {
                $checkboxes = $checkbox;
            }
            $checkboxes.each(function() {
                var $checkbox = $(this),
                    klass = 'hide-' + $checkbox.attr('name');
                if (is_all) { $checkbox.prop('checked', checked); }
                $feed.toggleClass(klass, !checked);
            });
            Activity.toggle_empty_parts($feed);
            return false;
        }), // on_filter_change

        on_filter_link_click: (function Activity__on_filter_link_click (ev) {
            // avoid propagation to bootstrap dropdown which would close the dropdown
            ev.stopPropagation();
        }), // on_filter_link_click

        toggle_empty_parts: (function Activity__toggle_empty_parts ($feed) {
            var checked_filters = [],
                $inputs = $feed.find('.activity-filter input:checked');
            for (var i = 0; i < $inputs.length; i++) {
                checked_filters.push('.' + $inputs[i].name);
            }
            var filter = checked_filters.join(', '),
                no_filter = checked_filters.length == 0,
                $sections = $feed.find('.box-section');
            for (var j = 0; j < $sections.length; j++) {
                var $section = $($sections[j]);
                $section.toggleClass('hidden', no_filter || $section.children('ul').children(filter).length == 0);
            }
            if ($feed.hasClass('for-repositories')) {
                var $repositories = $feed.find('.activity-repository');
                for (var k = 0; k < $repositories.length; k++) {
                    var $repository = $($repositories[k]);
                    $repository.toggleClass('hidden', no_filter || $repository.children('.box-content').children(':not(.hidden)').length == 0);
                }
            }
        }), // toggle_empty_parts

        init_feeds: (function Activity__init_feeds () {
            setInterval(function() {
                var $feeds = $(Activity.selectors.main);
                for (var i = 0; i < $feeds.length; i++) {
                    time_ago.replace($feeds[i]);
                }
            }, 60000);

            var $feeds = $(Activity.selectors.main);
            for (var j = 0; j < $feeds.length; j++) {
                Activity.toggle_empty_parts($($feeds[j]));
            }
        }), // init_feeds

        init_events: (function Activity__init_events () {
            $document.on('click', Activity.selectors.main + ' ' + Activity.selectors.issue_link, Ev.stop_event_decorate(Activity.on_issue_link_click));
            $document.on('click', Activity.selectors.main + ' ' + Activity.selectors.buttons.refresh, Ev.stop_event_decorate(Activity.on_refresh_button_click));
            $document.on('click', Activity.selectors.main + ' ' + Activity.selectors.buttons.more, Ev.stop_event_decorate(Activity.on_more_button_click));
            $document.on('click', Activity.selectors.main + ' ' + Activity.selectors.filter_links, Ev.stop_event_decorate(Activity.on_filter_link_click));
            $document.on('change', Activity.selectors.main + ' ' + Activity.selectors.filter_checkboxes, Ev.stop_event_decorate(Activity.on_filter_change));
        }), // init_events

        init: (function Activity__init () {
            Activity.init_feeds();
            Activity.init_events();
        }) // init
    }; // Activity
    Activity.init();
    window.Activity = Activity;

    var HoverIssue = {
        selector: '.hoverable-issue',
        abort_selector: '.not-hoverable',
        activated: true,
        delay_enter: 500,
        popover_options: null,  // defined in init

        extract_issue_ident: function ($node) {
            var data = $node.data();
            if (data.repository && data.issueNumber) {
                return {
                    repository: data.repository,
                    issueNumber: data.issueNumber
                };
            }
            return null;

        }, // extract_issue_ident

        get_issue_ident: function ($node) {
            var ident = $node.data('hover-ident');
            if (!ident) {
                // check directly on the node
                ident = HoverIssue.extract_issue_ident($node);
                // find a parent with the ident
                if (!ident) {
                    var parents = $node.parents();
                    for (var i = 0; i < parents.length; i++) {
                        ident = HoverIssue.extract_issue_ident($(parents[i]));
                        if (ident) {
                            break;
                        }
                    }
                }
                if (ident) {
                    $node.data('hover-ident', ident);
                }
            }
            return ident;
        }, // get_ident_parent

        get_popover_options: function ($node) {
            var node = $node[0],
                ident = HoverIssue.get_issue_ident($node),
                placement = HoverIssue.popover_options.placement,
                $parent_popover, parent_node,
                onShow = null, child_popover_left = null;

            if ($node.data('popover-placement')) {
                placement = $node.data('popover-placement');
            } else if ($node.closest('#github-notifications-menu').length) {
                placement = 'bottom';
            } else if ($node.closest('.issue-item, .activity-feed').length) {
                placement = 'horizontal';
            } else {
                $parent_popover = $node.closest('.webui-popover-hover-issue');
                if ($parent_popover.length) {
                    parent_node = $parent_popover.data('trigger-element')[0];
                    if (!parent_node.hover_issue_popover_trigger_childs) {
                        parent_node.hover_issue_popover_trigger_childs = [];
                    }
                    parent_node.hover_issue_popover_trigger_childs.push(node);
                    node.hover_issue_popover_trigger_parent = parent_node;

                    placement = 'vertical';

                    onShow = function($popover) {
                        // move the new popover at the same level than the parent popover
                        var $parent_popover = $node.closest('.webui-popover-hover-issue.in');
                        if ($parent_popover.length) {
                            // we save the var because on the first show, and the second show
                            // (onsuccess), the original popover may have disappeared
                            child_popover_left = $parent_popover.css('left');
                        }
                        if (child_popover_left != null) {
                            $popover.css({left: child_popover_left});
                        }
                    }
                }
            }

            if (ident) {
                return $.extend({}, HoverIssue.popover_options, {
                    type: 'async',
                    async: {
                        type: 'GET',
                        success: function(that, data) {
                            if (onShow) { onShow(that.getTarget()); }
                            var $content_element = that.getContentElement(),
                                $content = $content_element.find('.issue-content');
                            $content_element.toggleClass('with-repository', $content.data('repository') != main_repository);
                            $content.find('header h3 > a').addClass('issue-link')
                                                          .attr('title', 'Click to open full view')
                                                          .click($.proxy(HoverIssue.force_close_popover, node));
                            var $count = $content.find('.issue-comments-count');
                            $count.replaceWith($('<span/>').attr('class', $count.attr('class'))
                                                           .attr('title', $count.attr('title'))
                                                           .html($count.html()));
                            MarkdownManager.update_links($content);
                        },
                        error: function(that, xhr, data) {
                            if (xhr.status) { // if no status, it's an abort
                                that.setContent('<div class="alert alert-error"><p>Unable to get the issue. Possible reasons are:</p><ul>' +
                                    '<li>You are not allowed to see this issue</li>' +
                                    '<li>This issue is not on a repository you subscribed on ' + window.software.name + '</li>' +
                                    '<li>The issue may have been deleted</li>' +
                                    '<li>Connectivity problems</li>' +
                                    '</ul></div>');
                                that.getTarget().addClass('webui-error');
                            }
                        }
                    },
                    url: '/' + ident.repository + '/issues/' + ident.issueNumber + '/preview/',
                    content: '<div>Repository: ' + ident.repository + '<br/>Issue: ' + ident.issueNumber + '</div>',
                    placement: placement,
                    onShow: onShow
                });
            } else {
                return $.extend({}, HoverIssue.popover_options, {
                    type: '',
                    async: false,
                    content: '<div class="alert alert-error">A problem occurred when we wanted to retrieve the issue content :(</div>',
                    placement: placement,
                    onShow: function($element) {
                        if (onShow) { onShow($element); }
                        $element.addClass('webui-error');
                    }
                });
            }
        }, // get_popover_options

        display_popover: function (node) {
            var $node = $(node),
                old_url = $node.attr('data-url');
            if (old_url) { $node.removeAttr('data-url'); }

            $node.webuiPopover(HoverIssue.get_popover_options($node))
                 .webuiPopover('show');

            node.hover_issue_popover = $node.data('plugin_webuiPopover');

            node.hover_issue_popover.getTarget().on({
                     mouseenter: function() { if ($(this).hasClass('in')) { $.proxy(HoverIssue.on_mouseenter, this)(); } },
                     mouseleave: HoverIssue.on_mouseleave
                 });

            if (old_url) { $node.attr('data-url', old_url); }
        }, // display_popover

        force_close_popover: function () {
            var node = this;
            setTimeout(function() {
                node.hover_issue_is_hover = false;
                if (node.hover_issue_popover) {
                    HoverIssue.remove_popover(node, true);
                }
            }, 3);
        }, // force_close_popover

        remove_popover: function (node, fast) {
            var popover = node.hover_issue_popover;
            node.hover_issue_popover = null;

            if (node.hover_issue_popover_trigger_parent) {
                var parent_node = node.hover_issue_popover_trigger_parent;
                var index = parent_node.hover_issue_popover_trigger_childs.indexOf(node);
                if (index != -1) {
                    parent_node.hover_issue_popover_trigger_childs.splice(index, 1);
                }
                if (!parent_node.hover_issue_popover_trigger_childs.length) {
                    delete parent_node.hover_issue_popover_trigger_childs;
                }
                delete node.hover_issue_popover_trigger_parent;
            }

            var $target = popover.getTarget();

            if ($target.length) {
                if (fast) { $target.removeClass('fade'); }
                $target.off({
                    mouseenter: HoverIssue.on_mouseenter,
                    mouseleave: HoverIssue.on_mouseleave
                });
            }

            $(node).off('mouseleave', HoverIssue.on_mouseleave);

            popover.options.onHide = function() {
                setTimeout(function() {
                    popover.destroy();
                    delete node.hover_issue_is_hover;
                    delete node.hover_issue_popover;
                    if (node.hover_issue_popover_trigger_parent) {
                        delete node.hover_issue_popover_trigger_parent;
                    }
                    if (node.hover_issue_popover_trigger_childs) {
                        delete node.hover_issue_popover_trigger_childs;
                    }
                }, fast ? 0 : 300);
            };

            popover.hide();
        },

        get_node_from_node_or_popover: function (node) {
            var $node = $(node);
            return $node.hasClass('webui-popover') ? $node.data('trigger-element')[0] : node;
        }, // get_hover_node

        on_delayed_mouseenter: function () {
            if (HoverIssue.activated && this.hover_issue_is_hover && !this.hover_issue_popover) {
                HoverIssue.display_popover(this);
            }
        }, // on_delayed_mouseenter

        on_mouseenter: function () {
            if (!HoverIssue.activated) { return; }
            var node = HoverIssue.get_node_from_node_or_popover(this);
            $(node).off('mouseleave', HoverIssue.on_mouseleave)
                   .on('mouseleave', HoverIssue.on_mouseleave);
            node.hover_issue_is_hover = true;
            setTimeout($.proxy(HoverIssue.on_delayed_mouseenter, node), HoverIssue.delay_enter);
        }, // on_mouseenter

        on_delayed_mouseleave: function () {
            if (!this.hover_issue_is_hover && this.hover_issue_popover && !this.hover_issue_popover_trigger_childs) {
                HoverIssue.remove_popover(this);
            }
        }, // on_delayed_mouseleave

        on_mouseleave: function () {
            var node = HoverIssue.get_node_from_node_or_popover(this);
            node.hover_issue_is_hover = false;
            setTimeout($.proxy(HoverIssue.on_delayed_mouseleave, node), 500);
        }, // on_mouseleave

        on_abort_mouseenter: function () {
            var $abort_node = $(this),
                node = $abort_node.closest(HoverIssue.selector)[0];
            $.proxy(HoverIssue.force_close_popover, node)();
        }, // on_abort_mouseenter

        on_abort_mouseleave: function () {
            var $abort_node = $(this),
                $node = $abort_node.closest(HoverIssue.selector);
            setTimeout(function() {
                if ($node.is(':hover')) {
                    $.proxy(HoverIssue.on_mouseenter, $node[0])();
                }
            }, 100);
        }, // on_abort_mouseleave

        deactivate: function () {
            var $popovers = $('.webui-popover-hover-issue.in');
            for (var i = 0; i < $popovers.length; i++) {
                var node = HoverIssue.get_node_from_node_or_popover($popovers[i]);
                $.proxy(HoverIssue.force_close_popover, node)();
            }
            HoverIssue.activated = false;
        }, // deactivate

        reactivate: function () {
            HoverIssue.activated = true;
        }, // reactivate

        init_events: function () {
            $document.on('mouseenter', HoverIssue.selector, HoverIssue.on_mouseenter);
            $document.on('mouseenter', HoverIssue.abort_selector, HoverIssue.on_abort_mouseenter);
            $document.on('mouseleave', HoverIssue.abort_selector, HoverIssue.on_abort_mouseleave);
            $document.on('click', HoverIssue.selector, HoverIssue.force_close_popover);
            $document.on('sortstart', HoverIssue.deactivate);
            $document.on('sortstop', HoverIssue.reactivate);
        }, // init_events

        init: function () {
            HoverIssue.popover_options = {
                type: 'html',
                trigger: 'manual',
                async: true,
                placement: 'horizontal',
                multi: true,
                arrow: false,
                padding: false,
                width: '40%',
                animation: 'fade',
                // Use our own spinner
                template: '<div class="webui-popover webui-popover-hover-issue">' +
                    '<div class="webui-arrow"></div>' +
                    '<div class="webui-popover-inner">' +
                    '<a href="#" class="close"></a>' +
                    '<h3 class="webui-popover-title"></h3>' +
                    '<div class="webui-popover-content"><p class="empty-area"><i class="fa fa-spinner fa-spin"> </i></p></div>' +
                    '</div>' +
                    '</div>'
            };

            HoverIssue.init_events();
        } // init

    }; // HoverIssue
    HoverIssue.init();
    window.HoverIssue = HoverIssue;

    $.extend(GithubNotifications, {
        item_selector: '.issue-item-notification',
        default_error_msg: 'Internal problem: we were unable to update your notification',
        spin: '<span class="spin-holder"><i style="" class="fa fa-spinner fa-spin"> </i></span>',
        $count_node: $('#github-notifications-count'),
        $menu_node: $('#github-notifications-menu'),
        $menu_node_counter: null,
        current_count: 0,
        previous_count: 0,
        orig_count: null,
        orig_last: null,
        orig_date: null,
        hash: null,
        last_url: null,

        disable_form: function ($form) {
            var $inputs = $form.find('input[type=checkbox]');
            $form.data('disabled', true);
            // disable the iCheck widget
            $inputs.iCheck('disable');
            // disabled input will be ignored by serialize, so just set them
            // readonly
            $inputs.prop('readonly', true);
            $inputs.prop('disabled', false);
            $form.find(':button').prop('disabled', true);
        }, // disable_form

        enable_form: function ($form) {
            var $inputs = $form.find('input[type=checkbox]');
            $form.find('.spin-holder').remove();
            $inputs.prop('disabled', true); // needed for iCheck to re-enable them
            $inputs.iCheck('enable');
            $inputs.prop('readonly', false);
            $form.find(':button').prop('disabled', false);
            $form.data('disabled', false);
        }, // enable_form

        save_values: function ($form, values) {
            var $inputs;
            if (!values) {
                values = {};
                $inputs = $form.find('input[type=checkbox]');
                $inputs.each(function () {
                    values[this.name] = this.checked;
                });
            }
            $form.data('previous-values', values);
        }, // save_values

        apply_values: function ($form, values) {
            var $inputs = $form.find('input[type=checkbox]');
            if (!values) {
                values = $form.data('previous-values');
            }
            $.each($form.data('previous-values'), function(k, v) {
                $inputs.filter('[name=' + k + ']').iCheck(v ? 'check' : 'uncheck');
            });
        }, // apply_values

        on_checkbox_changed: function(ev) {
            ev.stopPropagation();
            var $checkbox = $(this),
                $form = $checkbox.closest('form');
            if ($form.data('disabled')) { return; }
            $checkbox.parent().append(GithubNotifications.spin);
            GithubNotifications.disable_form($form);
            GithubNotifications.post_form($form)
        },

        post_form: function ($form) {
            var data = $form.serialize();
            var action = $form.attr('action');
            $.post(action, data)
                .done($.proxy(GithubNotifications.on_post_submit_done, $form))
                .fail($.proxy(GithubNotifications.on_post_submit_failed, $form))
                .always(function () { GithubNotifications.enable_form($form); });
        }, // post_form

        on_mark_as_read_in_notification_menu_click: function(ev) {
            var $link = $(this),
                data = {
                    read: 1,
                    active: $link.data('active') ? 1 : 0,
                    csrfmiddlewaretoken: $body.data('csrf')
                },
                $li = $link.parent(),
                $ul = $li.parent(),
                action = $ul.data('edit-url'),
                $form = null;

            if (!action) { return; }

            ev.stopPropagation();
            ev.preventDefault();

            if ($li.hasClass('disabled')) { return; }
            $li.addClass('loading');

            $ul.find('li.with-mark-notification-as-read-link').addClass('disabled');

            if (GithubNotifications.on_page) {
                $form = $('form[action="' + action + '"]');
                if ($form.length) {
                    GithubNotifications.disable_form($form);
                } else {
                    $form = null;
                }
            }

            $.post(action, data)
                .done($.proxy(GithubNotifications.on_post_submit_done, $form))
                .fail($.proxy(GithubNotifications.on_post_submit_failed, $form))
                .fail(function() {
                    $ul.find('li.with-mark-notification-as-read-link').removeClass('disabled loading');
                })
                .always(function () {if ($form) { GithubNotifications.enable_form($form); }});

        }, // on_mark_as_read_in_notification_menu_click

        on_post_submit_done: function (data) {
            var $form = this;
            if (!data || !data.status) {
                data = {status: 'KO', error_msg: default_error_msg};
            }
            if (data.status != 'OK') {
                return $.proxy(GithubNotifications.on_post_submit_failed, $form)({}, data);
            }

            if ($form) {
                GithubNotifications.save_values($form, data.values);
                GithubNotifications.apply_values($form, data.values);
                $form.find('[data-filter^="active:"]').data('filter', 'active:' + (data.values.active ? 'yes' : 'no'));
                $form.find('[data-filter^="unread:"]').data('filter', 'unread:' + (data.values.read ? 'no' : 'yes'));
                $form.data('manual-unread', data.manual_unread);
            }

            GithubNotifications.on_notifications_ping(null, null, {
                count: data.count,
                last: data.last,
                hash: data.hash
            });

        }, // on_post_submit_done

        on_post_submit_failed: function (xhr, data) {
            var $form=this,
                error_msg = data.error_msg || GithubNotifications.default_error_msg;
            MessagesManager.add_messages([MessagesManager.make_message(error_msg, 'error')]);
            if ($form) { GithubNotifications.apply_values($form, data.values); }
            if (data.values) {
                GithubNotifications.on_notifications_ping(null, null, {
                    count: data.count,
                    last: data.last,
                    hash: data.hash
                });
            }
        }, // on_post_submit_failed

        on_current_issue_toggle_event: function (check) {
            var decorator = function() {
                if (!IssuesList.current) { return; }
                if (!IssuesList.current.current_group) { return; }
                if (!IssuesList.current.current_group.current_issue) { return; }
                var $input = IssuesList.current.current_group.current_issue.$node.find(
                    GithubNotifications.item_selector + ' input[type=checkbox][name=' + check + ']:visible');
                if ($input.length) {
                    return GithubNotifications.toggle_check($input);
                }
            };
            return Ev.key_decorate(decorator);
        }, // on_current_issue_event

        toggle_check: function($input) {
            $input.iCheck('toggle');
            return false;
        }, // toggle_read

        init_item_forms: function() {
            if (!GithubNotifications.on_page) { return; }
            var $forms = $(GithubNotifications.item_selector + ' form:not(.js-managed)'),
                $checkboxes = $forms.find('input[type=checkbox]');
            $forms.each(function() { GithubNotifications.save_values($(this));});
            $checkboxes.iCheck({checkboxClass: 'icheckbox_flat-blue'});
            $checkboxes.on('ifChecked ifUnchecked ifToggled', GithubNotifications.on_checkbox_changed);
            $forms.on('click', '.spin-holder', Ev.cancel);
            $forms.addClass('js-managed');
        }, // init_item_forms

        init_subscription: function() {
            WS.subscribe(
                'gim.front.user.' + WS.user_topic_key + '.notifications.ping',
                'GithubNotifications.on_notifications_ping',
                GithubNotifications.on_notifications_ping,
                'exact'
            );
            if (GithubNotifications.on_page) {
                WS.subscribe(
                    'gim.front.user.' + WS.user_topic_key + '.notifications.issue',
                    'GithubNotifications__on_issue',
                    GithubNotifications.on_notification_updated,
                    'exact'
                );
            }
        }, // init_subscription

        on_notification_updated: function(topic, args, kwargs) {
            if (!kwargs.model || kwargs.model != 'Issue' || !kwargs.id || !kwargs.url) { return; }
            var issue = IssuesList.get_issue_by_id(kwargs.id);
            if (issue) {
                var $form = issue.$node.find(GithubNotifications.item_selector + ' form'),
                    values = {read: kwargs.read, active: kwargs.active};
                GithubNotifications.save_values($form, values);
                GithubNotifications.apply_values($form, values);
            }

            IssuesList.on_update_alert(topic, args, kwargs);
        }, // on_notification_updated

        on_notifications_ping: function (topic, args, kwargs) {
            var $node = GithubNotifications.$count_node,
                old_count = GithubNotifications.current_count,
                old_last = $node.data('last'),
                old_date = null,
                new_count = kwargs.count || 0,
                new_last = kwargs.last,
                new_date = null,
                to_notify = false,
                old_hash = GithubNotifications.hash,
                new_hash = kwargs.hash;

            // reload last 10 if needed
            if (new_hash != old_hash) {
                GithubNotifications.hash = new_hash;
                GithubNotifications.$menu_node.data('last-notifications-hash', new_hash);
                GithubNotifications.reload_last_ones();
            }

            GithubNotifications.current_count = new_count;

            if (new_count > old_count) {
                to_notify = true;
            } else {
                if (old_last) { old_date = new Date(old_last); }
                if (new_last) { new_date = new Date(new_last); }
                if (new_date && (!old_date || new_date > old_date)) {
                    to_notify = true;
                }
            }

            $node.data('count', new_count);
            $node.text(new_count);
            $node.toggleClass('no-notifications', !new_count);
            $node.data('last', new_last);
            GithubNotifications.$menu_node.attr('title', new_count ? ("You have " + new_count + " unread notification" + (new_count > 1 ? 's' : '')) : "You don't have unread notifications");
            GithubNotifications.$menu_node_counter.text(new_count).toggleClass('label-dark-red', new_count > 0);

            // remove the animation if back to normal
            if ((!new_last || GithubNotifications.orig_last && new_date <= GithubNotifications.orig_date)
                && (new_count <= GithubNotifications.orig_count)) {
                to_notify = false;
                $node.removeClass('new-notifications');
            }

            if (to_notify) {
                $node.addClass('new-notifications');
            }

            // new info are now the reference
            GithubNotifications.orig_count = new_count;
            GithubNotifications.orig_date = new_date;

            GithubNotifications.update_favicon();
        }, // on_notifications_ping

        update_favicon: function (force) {
            var count = GithubNotifications.current_count;
            if (!force && count == GithubNotifications.previous_count) { return; }
            GithubNotifications.previous_count = count;
            Favicon.set_val(count > 99 ? '99+' : count);
        }, // update_favicon

        reload_last_ones: function() {
            $.get(GithubNotifications.last_url).done(function (data) {
                var $list = $('#github-notifications-menu-list');
                if (data) {
                    if (!$list.length) {
                        GithubNotifications.$menu_node.addClass('dropdown-submenu pull-left');
                        $list = $('<ul class="dropdown-menu" id="github-notifications-menu-list" title=""></ul>');
                        GithubNotifications.$menu_node.append($list);
                    }
                    $list.replaceWith(data);
                } else {
                    $list.remove();
                    GithubNotifications.$menu_node.removeClass('dropdown-submenu pull-left');
                }
            });
        },

        init: function () {
            if (GithubNotifications.$count_node.length) {
                GithubNotifications.current_count = parseInt(GithubNotifications.$count_node.data('count') || 0, 10);
                GithubNotifications.$menu_node_counter = GithubNotifications.$menu_node.find('span.label');
                GithubNotifications.orig_count = GithubNotifications.current_count;
                GithubNotifications.orig_last = GithubNotifications.$count_node.data('last');
                if (GithubNotifications.orig_last) {
                    GithubNotifications.orig_date = new Date(GithubNotifications.orig_last);
                }
                GithubNotifications.hash = GithubNotifications.$menu_node.data('last-notifications-hash');
                GithubNotifications.last_url = GithubNotifications.$menu_node.data('last-notifications-url');
                GithubNotifications.init_subscription();
            }
            $document.on('click', 'li.with-mark-notification-as-read-link:not(.disabled) a', GithubNotifications.on_mark_as_read_in_notification_menu_click);
            if (!GithubNotifications.on_page) { return; }
            GithubNotifications.init_item_forms();
            jwerty.key('shift+r', GithubNotifications.on_current_issue_toggle_event('read'));
            jwerty.key('shift+a', GithubNotifications.on_current_issue_toggle_event('active'));
        } // init

    }); // GithubNotifications

    GithubNotifications.init();

    // disable clicking on disabled item
    $document.on('click', '.disabled, [disabled], .disabled > *, [disabled] > *', function(e) {
        Ev.cancel(e);
    });

    // if there is a collapse inside another, we don't want fixed heights, so always remove them
    $document.on('shown.collapse', '.collapse', function() {
        $(this).css('height', 'auto');
    });

    // if a link is on a collapse header, deactivate the collapse on click
    $document.on('click', '[data-toggle=collapse] a:not([href=#])', function(ev) {
        ev.stopPropagation();
    });
    // if a link is a collapse header, deactivate the real click
    $document.on('click', 'a[data-toggle=collapse]', function(ev) {
        ev.preventDefault();
    });
    // if a link is "fake" and in a collapse header, deactivate the real click
    $document.on('click', '[data-toggle=collapse] a[href=#]', function(ev) {
        ev.preventDefault();
    });

});

