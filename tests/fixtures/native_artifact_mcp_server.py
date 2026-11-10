"""Reviewed read-only AE fixture for the native result transport acceptance.

This is a test server, never a product option/tool. Only font-inventory jobs are
augmented; no project/layer/queue is opened, saved, edited or rendered.
"""
import json
from astra_video_studio import mcp_server
from astra_video_studio.ae_bridge import runner
from astra_video_studio.ae_bridge.templates import render_script


def fixture_template(action, payload):
    script = render_script(action, payload)
    if action != 'design_fonts': return script
    marker = "        result.status = 'succeeded';"
    assert script.count(marker) == 1
    large = payload['query']['query'] == 'AstraTransportLargeFixture'
    fixture = '''
        function transportFixtureState() {
            var state = {file:null, dirty:null, queue_items:0, items:[]}, i, j, item, layers;
            if (!app.project) { return state; }
            state.file = app.project.file ? app.project.file.fsName : null;
            state.dirty = app.project.dirty;
            state.queue_items = app.project.renderQueue.numItems;
            for (i=1;i<=app.project.numItems;i++) {
                item = app.project.item(i);
                var record = {id:item.id, name:item.name, comment:item.comment};
                if (item instanceof CompItem) {
                    record.width=item.width;record.height=item.height;record.fps=item.frameRate;record.duration=item.duration;record.layers=[];
                    for(j=1;j<=item.numLayers;j++) {
                        var layer=item.layer(j);
                        record.layers.push({id:layer.id,name:layer.name,comment:layer.comment,locked:layer.locked,enabled:layer.enabled,
                            in_point:layer.inPoint,out_point:layer.outPoint,start_time:layer.startTime});
                    }
                }
                state.items.push(record);
            }
            return state;
        }
        result.data.active_project_fixture = transportFixtureState();
        result.data.fixture_unicode = __UNICODE_LITERAL__;
        var fixtureString = '0123456789ABCDEF';
        for (var fi=0;fi<__DOUBLINGS__;fi++) { fixtureString += fixtureString; }
        result.data.transport_fixture = {read_only:true,payload:fixtureString};
'''.replace('__DOUBLINGS__', '17' if large else '0').replace('__UNICODE_LITERAL__', json.dumps('Ação 😀 日本語\nLine two', ensure_ascii=True))
    if payload['query']['query'] == 'AstraTransportFailureFixture':
        fixture += "\n        throw new Error('EXPECTED_READ_ONLY_NATIVE_FIXTURE_FAILURE');\n"
    return script.replace(marker, fixture + '\n' + marker)


runner.render_script = fixture_template
mcp_server.main()
