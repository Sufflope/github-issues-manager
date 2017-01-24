$().ready(function() {

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
});
