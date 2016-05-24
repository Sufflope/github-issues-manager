var Onboarding = {
    user_data: window.onboarding_user_data,
    variables: window.onboarding_variables,

    topics: {
        main_dashboard_no_subscriptions: 14274, //  will redirect to ``main_dashboard_has_subscriptions`` if there is subscriptions
        main_dashboard_has_subscriptions: 15638, //  will redirect to ``main_dashboard_no_subscriptions`` if there is no subscriptions
        subscriptions_chooser: 15689,
        repository_dashboard: 15701
    },

    with_subscriptions_topics: [
        'repository_dashboard'
    ],

    current_keydown_callback: null,
    last_displayed_step: null,

    /********************/
    /* Public functions */
    /********************/

    has_subscriptions: function() {
        /** Tells if the current user has some subscriptions
         *
         *  Returns
         *  -------
         *  boolean
         *      ``true`` if the user has some subscriptions, ``false`` otherwise
         */

        return Onboarding.variables.subscriptions_count > 0;

    }, // has_subscriptions

    has_no_subscriptions: function() {
        /** Tells if the current user has no subscriptions
         *
         *  Returns
         *  -------
         *  boolean
         *      ``true`` if the user has no subscriptions, ``false`` otherwise
         */

        return !Onboarding.has_subscriptions()

    }, // has_no_subscriptions

    conditional_goto: function(player, topic_id, step_id, data) {
        /** Go to a step on the given topic, or a new topic, following a condition defined in `data`
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player from InlineManual
         *  topic_id: int
         *      The id of the topic currently being played
         *  step_id: int
         *      The current step being played
         *  data: dict
         *      Some data to define the condition and the step/topic to go to:
         *      - type: string ('function'|'selector')
         *          The type of condition to check:
         *          - function: A function of the ``Onboarding`` object will be called, without
         *              arguments. It should return a boolean that will be used as the result of
         *              the condition.
         *          - selector: A jquery selector to check on the page. If found, the condition is
         *              considered met.
         *      - function: string
         *          Name of the function to call if `type` is 'function'
         *      - selector: string
         *          Selector to use if `type` is 'selector
         *      - not
         *          If set and "truthy", the condition will be reversed
         *      - topic_true: string
         *          The name of the topic to go if the final condition is truthy. It must be an entry
         *          of ``Onboarding.topics``
         *      - topic_false: string
         *          The name of the topic to go if the final condition is falsy. It must be an entry
         *          of ``Onboarding.topics``
         *      - step_true: integer
         *          The step to go to if the final condition is truthy
         *      - step_false: integer
         *          The step to go to if the final condition is falsy
         *      - step_backward_true: integer
         *          The step to go to if the final condition is truthy and we are in backward mode
         *      - step_backward_false: integer
         *          The step to go to if the final condition is falsy and we are in backward mode
         *
         */

        step_id = parseInt(step_id, 10);

        var condition_met = false,
            is_backward = Onboarding.last_displayed_step && Onboarding.last_displayed_step > step_id,
            goto_step, goto_topic;

        if (typeof data.type !== 'undefined') {
            switch (data.type) {
                case 'function':
                    if (typeof data.function !== 'undefined' && typeof Onboarding[data.function] !== 'undefined') {
                        condition_met = Onboarding[data.function]();
                    }
                    break;
                case 'selector':
                    if (typeof data.selector !== 'undefined') {
                        condition_met = $(data.selector).length > 0;
                    }
                    break;
            }
        }

        if (typeof data.not !== 'undefined' && data.not) {
            condition_met = !condition_met;
        }

        if (condition_met && is_backward && typeof data.step_backward_true !== 'undefined') {
            goto_step = data.step_backward_true;
        } else if (condition_met && !is_backward && typeof data.step_true !== 'undefined') {
            goto_step = data.step_true;
        } else if (!condition_met && is_backward && typeof data.step_backward_false !== 'undefined') {
            goto_step = data.step_backward_false;
        } else if (!condition_met && !is_backward && typeof data.step_false !== 'undefined') {
            goto_step = data.step_false;
        }

        if (condition_met  && typeof data.topic_true !== 'undefined') {
            goto_topic = data.topic_true;
        } else if (!condition_met && typeof data.topic_false !== 'undefined') {
            goto_topic = data.topic_false;
        }

        if (goto_topic && typeof Onboarding.topics[goto_topic] !== 'undefined') {
            goto_topic = Onboarding.topics[goto_topic];
        } else {
            goto_topic = null;
        }

        if (goto_step) {
            goto_step = parseInt(goto_step);
            if (isNaN(goto_step)) {
                goto_step = null;
            }
        }

        if (goto_topic) {
            if (goto_step) {
                player.activateStep(goto_topic, goto_step);
                return false;
            } else {
                player.activateTopic(goto_topic);
                return false;
            }
        } else if (goto_step) {
            player.goToStep(goto_step);
            return false;
        }

    }, // conditional_goto

    scroll_top: function(player, topic_id, step_id, data) {
        /** Scroll to top the element defined in  ``data.selector``
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player from InlineManual
         *  topic_id: int
         *      The id of the topic currently being played
         *  step_id: int
         *      The current step being played
         *  data: dict
         *      Only one key:
         *      - selector: string
         *          The selector on which ``scrollTop(0)`` will be called.
         *
         */

        if (typeof data.selector === 'undefined') { return; }

        $(data.selector).scrollTop(0);

    }, // scroll_top

    /**********************/
    /* Internal functions */
    /**********************/

    prepare_player : function(player) {
        /** Initialize the player options
         *
         *  Parameters
         *  ----------
         *  player: list or imPlayer
         *      The player if initialized, else a list that will be used by the player when ready
         */

        var callbacks = {
            onInit: Onboarding.on_player_init,
            onTopicStart: Onboarding.on_player_topic_start,
            onTopicEnd: Onboarding.on_player_topic_end,
            onStepShow: Onboarding.on_player_step_show
        };
        player.push(['setCallbacks', callbacks]);

        // var options = {
        // };
        //
        // player.push(['setOptions', options]);

    }, // prepare_player

    is_topic_done: function(player, topic_id) {
        /** Tells if the given topic was already completed by the current user
         *
         *  Parameters
         *  ----------
         *  topic_id: int or str
         *      The identifier of the topic to check
         *
         *  Returns
         *  -------
         *  boolean
         *      ``true`` if the topic was already completed, ``false`` otherwise
         */

        topic_id = parseInt(topic_id, 10);
        try {
            return player.metadata.topics[topic_id].completions > 0;
        } catch(e) {
            return false;
        }
    }, // is_topic_done

    go_to_previous_step_of_current_topic: function(player) {
        /** Tell the player to go to the previous step of the current topic
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player currently playing a topic
         *
         */

        player.goToStep('previous');

    }, // go_to_previous_step_of_current_topic

    go_to_next_step_of_current_topic: function(player) {
        /** Tell the player to go to the next step of the current topic
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player currently playing a topic
         *
         */

        player.goToStep('next');

    }, // go_to_next_step_of_current_topic

    go_to_first_step_of_current_topic: function(player) {
        /** Tell the player to go to the first step of the current topic
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player currently playing a topic
         *
         */

        player.goToStep(0);

    }, // go_to_first_step_of_current_topic

    go_to_last_step_of_current_topic: function(player) {
        /** Tell the player to go to the last step of the current topic
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player currently playing a topic
         *
         */

        player.goToStep(player.countTopicSteps(player.getCurrentTopic()) - 1);

    }, // go_to_last_step_of_current_topic

    exit_current_topic: function(player) {
        /** Tell the player to exit the topic currently being played
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player currently playing a topic
         *
         */

        player.deactivate();
        Onboarding.on_player_topic_end();

    }, // exit_current_topic

    autostart_topic: function(player, path) {
        /** Check the path to see if a topic not completed should be auto started
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player for which to launch the topic
         *  path: str
         *      The path for which to launch a topic
         */

        var topic_name = null, topic_id = null;

        // a topic previously started is currently being played
        if (player.getCurrentTopic()) { return; }

        // guess the topic
        switch (true) {
            case /^\/dashboard\/$/.test(path):
                // main dashboard

                if (Onboarding.has_subscriptions()) {
                    topic_name = 'main_dashboard_has_subscriptions';
                } else {
                    topic_name = 'main_dashboard_no_subscriptions';
                }
                break;

            case /^\/dashboard\/repositories\/choose\/$/.test(path):
                // repositories chooser
                topic_name = 'subscriptions_chooser';
                break;

            case /^\/[\w\-\.]+\/[\w\-\.]+\/dashboard\/$/.test(path):
                // repository dashboard
                topic_name = 'repository_dashboard';
                break

        } // switch

        // no topic for this path, we can stop here
        if (!topic_name || typeof Onboarding.topics[topic_name] === 'undefined') { return; }

        topic_id = Onboarding.topics[topic_name];

        // only launch the topic if not already complete
        if (Onboarding.is_topic_done(player, topic_id)) { return; }

        // now we can start the topic for the current patch
        player.activateTopic(topic_id);

    }, // autostart_topic

    hide_invalid_topics: function(player) {
        /** Hide some topics that the current user cannot access
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player for which to launch the topic
         */

        var need_redraw = false;

        if (!Onboarding.variables.subscriptions_count) {
            for (var i = 0; i < Onboarding.with_subscriptions_topics.length; i++) {
                var topic_name = Onboarding.with_subscriptions_topics[i],
                    topic_id = Onboarding.topics[topic_name];

                // remove the topic from the one we know about
                delete Onboarding.topics[topic_name];

                // hide it in the player
                player.topics[topic_id].hidden = true;

                // and stop it if currently playing
                if (parseInt(player.getCurrentTopic(), 10) == topic_id) {
                    player.deactivate();
                }

                need_redraw = true;
            }
        }

        if (need_redraw) {
            player.reinit();
        }

    }, // hide_invalid_topics

    correct_topics: function(player) {
        /** Hide some topics that the current user cannot access
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player for which to launch the topic
         */

        // set the correct url for the repository dashboard topic
        if (typeof Onboarding.topics.repository_dashboard !== 'undefined') {
            player.topics[Onboarding.topics.repository_dashboard].steps[0].path = Onboarding.variables.repository_dashboard_url;
        }

    }, // correct_topics

    on_keydown: function(event, player) {
        /** Called when a ``keydown`` event is called on ``document`
         *
         *  Parameters
         *  ----------
         *  event: Event
         *      The ``keydown`` event triggered
         *  player: imPlayer
         *      The player currently playing a topic
         *
         */

        var prevent = true;

        if (jwerty.is('←', event)) {
            Onboarding.go_to_previous_step_of_current_topic(player);
        } else if (jwerty.is('→', event)) {
            Onboarding.go_to_next_step_of_current_topic(player);
        } else if (jwerty.is('⇞', event)) {
            Onboarding.go_to_first_step_of_current_topic(player);
        } else if (jwerty.is('⇟', event)) {
            Onboarding.go_to_last_step_of_current_topic(player);
        } else if (jwerty.is('⎋', event)) {
            Onboarding.exit_current_topic(player);
        } else {
            prevent = false;
        }

        if (prevent) {
            return Ev.cancel(event);
        }
    }, // on_keydown

    on_player_init: function(player) {
        /** Called when the player is ready to be used.
         *
         *  We use this to auto-launch topics based on the current path, after having deactivated
         *  topics that are not accessible to the current user or updating them if needed.
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player that is now ready to use
         *
         */

        Onboarding.hide_invalid_topics(player);

        Onboarding.correct_topics(player);

        setTimeout(function () {
            Onboarding.autostart_topic(player, window.location.pathname);
        }, 500);

    }, // on_player_init

    on_player_topic_start: function(player, topic_id) {
        /** Called when a topic starts.
         *
         *  We use this to activate keyboard navigation
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player playing the topic
         *  topic_id: int or str
         *      The identifier of the topic that is starting
         */

        if (Onboarding.current_keydown_callback) {
            // will cancel the existing event if not already done
            Onboarding.on_player_topic_end();
        }

        Onboarding.current_keydown_callback = function(event) {
            Onboarding.on_keydown(event, player);
        };

        document.addEventListener('keydown', Onboarding.current_keydown_callback);

    }, // on_player_topic_start

    on_player_topic_end: function(player, topic_id) {
        /** Called when a topic ends.
         *
         *  We use this to deactivate keyboard navigation
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player playing the topic
         *  topic_id: int or str
         *      The identifier of the topic that is ending
         */

        document.removeEventListener('keydown', Onboarding.current_keydown_callback);
        Onboarding.current_keydown_callback = null;
        Onboarding.last_displayed_step = null;

    }, // on_player_topic_end

    on_player_step_show: function(player, topic_id, step_id) {
        /** Called when a step is displayed.
         *
         *  We use it to activate keyboard navigation if not already done.
         *  It is necessary because in some case, IM doesn't call ``onTopicStart`` when it
         *  automatically starts a topic.
         *
         *  Will also save the last displayed step
         *
         *  Parameters
         *  ----------
         *  player: imPlayer
         *      The player playing the topic
         *  topic_id: int or str
         *      The identifier of the topic that is currently being played
         *  step_id: int or str
         *      The identifier of the step that is displayed
         */

        if (!Onboarding.current_keydown_callback) {
            Onboarding.on_player_topic_start(player, topic_id);
        }

        Onboarding.last_displayed_step = step_id;

    }, // on_player_step_show

    init: function() {
        /** Initialize the onboarding process */

        // init inline-manual player to prepare actions
        window.inline_manual_player = window.inline_manual_player || [];

        // init inline-manual data
        window.inlineManualTracking = Onboarding.user_data;
        window.inlineManualOptions = {
            variables: Onboarding.variables
        };

        // actions to run when the player will be ready
        Onboarding.prepare_player(window.inline_manual_player);
    } // init

}; // Onboarding

Onboarding.init();
