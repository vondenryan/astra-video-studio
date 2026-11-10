// Trusted local idle dispatcher. Inbox accepts only UUIDs, never code or paths.
(function () {
    var config = /*ASTRA_BRIDGE_CONFIG*/null;
    if ($.global.__astraBridge && $.global.__astraBridge.task) {
        app.cancelTask($.global.__astraBridge.task);
    }
    var bridge = {root: config.workspace, instance_id: config.instance_id, active_job: null, task: null};
    function quote(value) {
        return '"' + String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
            .replace(/[\x00-\x1f]/g, function (c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
    }
    bridge.tick = function () {
        var heartbeat = new File(bridge.root + '/bridge/heartbeat.json'); heartbeat.encoding = 'UTF-8';
        if (heartbeat.open('w')) {
            try { heartbeat.write('{"instance_id":' + quote(bridge.instance_id) + ',"ae_version":' + quote(app.version)
                + ',"time_ms":' + new Date().getTime() + ',"active_job":' + (bridge.active_job ? quote(bridge.active_job) : 'null') + '}'); }
            finally { heartbeat.close(); }
        }
        if (!bridge.active_job) {
            var inbox = new File(bridge.root + '/bridge/inbox.txt');
            if (inbox.exists && inbox.open('r')) {
                var job = inbox.read().replace(/^\s+|\s+$/g, ''); inbox.close();
                if (/^[0-9a-f]{32}$/.test(job) && inbox.remove()) {
                    bridge.active_job = job;
                    var script = new File(bridge.root + '/jobs/' + job + '/operation.jsx');
                    try {
                        if (!script.exists) { throw new Error('Trusted job template not found'); }
                        $.evalFile(script); // Fixed workspace/jobs/<UUID>/operation.jsx only.
                    } catch (error) {
                        var result = new File(bridge.root + '/jobs/' + job + '/result.json'); result.encoding = 'UTF-8';
                        if (result.open('w')) {
                            try { result.write('{"operation_id":' + quote(job) + ',"status":"failed","data":{},"error":' + quote(String(error)) + '}'); }
                            finally { result.close(); }
                        }
                        bridge.active_job = null;
                    }
                }
            }
        }
        bridge.task = app.scheduleTask('$.global.__astraBridge.tick()', 250, false);
    };
    $.global.__astraBridge = bridge;
    bridge.tick();
}());
