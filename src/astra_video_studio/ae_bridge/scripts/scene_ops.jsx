// Fixed scene-edit helpers. All operation parameters are validated JSON data.
function sourceKind(layer) {
    if (!layer.source) { return null; }
    if (layer.source instanceof CompItem) { return 'composition'; }
    if (layer.source instanceof FootageItem) { return 'footage'; }
    return null;
}
function sourceHasMotion(layer) {
    if (sourceKind(layer) !== 'footage') { return false; }
    if (!layer.source.mainSource.isStill || layer.source.hasAudio) { return true; }
    return false;
}
function containsComp(source, destination, visited) {
    if (source.id - destination.id == 0) { return true; }
    if (visited[String(source.id)]) { return false; }
    visited[String(source.id)] = true;
    for (var i = 1; i <= source.numLayers; i++) {
        var layer = source.layer(i);
        if (sourceKind(layer) === 'composition' && containsComp(layer.source, destination, visited)) { return true; }
    }
    return false;
}
function blendValue(name) {
    if (name === 'normal') { return BlendingMode.NORMAL; }
    if (name === 'multiply') { return BlendingMode.MULTIPLY; }
    if (name === 'screen') { return BlendingMode.SCREEN; }
    if (name === 'add') { return BlendingMode.ADD; }
    throw new Error('Unsupported blend mode');
}
function blendName(value) {
    var names = ['normal', 'multiply', 'screen', 'add'], i;
    for (i = 0; i < names.length; i++) { if (Number(value) - Number(blendValue(names[i])) == 0) { return names[i]; } }
    return String(value);
}
function matteValue(name) {
    if (name === 'alpha') { return TrackMatteType.ALPHA; }
    if (name === 'alpha_inverted') { return TrackMatteType.ALPHA_INVERTED; }
    if (name === 'luma') { return TrackMatteType.LUMA; }
    if (name === 'luma_inverted') { return TrackMatteType.LUMA_INVERTED; }
    throw new Error('Unsupported matte mode');
}
function matteName(layer) {
    if (!layer.hasTrackMatte) { return 'none'; }
    var names = ['alpha', 'alpha_inverted', 'luma', 'luma_inverted'], i;
    for (i = 0; i < names.length; i++) { if (Number(layer.trackMatteType) - Number(matteValue(names[i])) == 0) { return names[i]; } }
    return String(layer.trackMatteType);
}
function animationSummary(root) {
    var info = {key_count: 0, expressions: 0};
    function walk(group) {
        for (var i = 1; i <= group.numProperties; i++) {
            var prop = group.property(i);
            if (prop.propertyType == PropertyType.PROPERTY) {
                info.key_count += prop.numKeys;
                if (prop.canSetExpression && prop.expression && prop.expression.length) { info.expressions++; }
            } else { walk(prop); }
        }
    }
    walk(root); return info;
}
function worldBasis(layer) {
    if (!isEditable2D(layer)) { return null; }
    function convert(point, node) {
        var pos = transform(node, 'position').valueAtTime(0, false), anchor = transform(node, 'anchor').valueAtTime(0, false);
        var scale = transform(node, 'scale').valueAtTime(0, false), rotation = transform(node, 'rotation').valueAtTime(0, false) * Math.PI / 180;
        var x = (point[0] - anchor[0]) * scale[0] / 100, y = (point[1] - anchor[1]) * scale[1] / 100;
        var result = [pos[0] + x * Math.cos(rotation) - y * Math.sin(rotation), pos[1] + x * Math.sin(rotation) + y * Math.cos(rotation)];
        return node.parent ? convert(result, node.parent) : result;
    }
    return [convert([0, 0], layer), convert([1, 0], layer), convert([0, 1], layer)];
}
function sceneComp(uuid) {
    var matches = [], i, item;
    for (i = 1; i <= app.project.numItems; i++) {
        item = app.project.item(i);
        if (item instanceof CompItem && identity('composition', item) === 'astra:composition:' + uuid) { matches.push(item); }
    }
    if (matches.length !== 1) { throw new Error('Composition absent/ambiguous'); }
    return matches[0];
}
function sceneLayer(comp, uuid) {
    var matches = [], i;
    for (i = 1; i <= comp.numLayers; i++) { if (identity('layer', comp.layer(i)) === 'astra:layer:' + uuid) { matches.push(comp.layer(i)); } }
    if (matches.length !== 1) { throw new Error('Layer absent/ambiguous'); }
    return matches[0];
}
function runSceneEdit() {
    var current = inspect(), q = p.request, ctx = p.context, action = p.scene_action, comp, layer, other, i;
    if (app.project.dirty !== false) { throw new Error('ACTIVE_PROJECT_PROTECTED'); }
    // Reject intervening edits after Python preflight, including saved manual changes.
    if (encode(current.compositions) !== encode(p.expected_state.compositions) || encode(current.footage) !== encode(p.expected_state.footage)) {
        throw new Error('STATE_CONFLICT: project changed after inspection');
    }
    var file = new File(p.version_path);
    if (file.exists) { throw new Error('OUTPUT_EXISTS'); }
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    if (action !== 'composition_create') { comp = sceneComp(q.composition_id); }
    if (q.layer_id) { layer = sceneLayer(comp, q.layer_id); }
    if (action === 'composition_layer_add' && containsComp(sceneComp(q.source_composition_id), comp, {})) {
        throw new Error('COMPOSITION_CYCLE');
    }
    app.project.save(file); p.project_path = p.version_path;
    var info = {action: action, moved_native_ids: []};
    app.beginUndoGroup('Astra ' + action);
    try {
        if (action === 'composition_create') {
            other = app.project.items.addComp(q.name, q.width, q.height, 1, q.duration, q.fps);
            other.bgColor = q.background; other.comment = 'astra:composition:' + ctx.new_composition_id;
        } else if (action === 'composition_update') {
            if (q.name !== null) { comp.name = q.name; }
            if (q.width !== null) { comp.width = q.width; }
            if (q.height !== null) { comp.height = q.height; }
            if (q.background !== null) { comp.bgColor = q.background; }
            if (q.fps !== null) { comp.frameRate = q.fps; }
            if (ctx.time_factor !== 1) {
                for (i = 1; i <= comp.numLayers; i++) {
                    other = comp.layer(i);
                    var oldStart = other.startTime, oldIn = other.inPoint, oldOut = other.outPoint;
                    other.startTime = oldStart * ctx.time_factor;
                    other.inPoint = oldIn * ctx.time_factor; other.outPoint = oldOut * ctx.time_factor;
                }
            }
            comp.duration = ctx.duration;
        } else if (action === 'null_create') {
            other = comp.layers.addNull(comp.duration); other.name = q.name; other.comment = 'astra:layer:' + ctx.new_layer_id;
        } else if (action === 'composition_layer_add') {
            other = comp.layers.add(sceneComp(q.source_composition_id));
            other.name = q.name; other.comment = 'astra:layer:' + ctx.new_layer_id;
            other.startTime = ctx.start_time; other.inPoint = ctx.start_time; other.outPoint = ctx.out_point;
        } else if (action === 'layer_duplicate') {
            other = layer.duplicate(); other.name = q.name; other.comment = 'astra:layer:' + ctx.new_layer_id;
        } else if (action === 'layer_remove') {
            layer.remove();
        } else if (action === 'layer_update') {
            if (q.name !== null) { layer.name = q.name; }
            if (q.blend_mode !== null) { layer.blendingMode = blendValue(q.blend_mode); }
            if (q.enabled !== null) { layer.enabled = q.enabled; }
            if (typeof ctx.start_time !== 'undefined') {
                layer.startTime = ctx.start_time; layer.inPoint = ctx.in_point; layer.outPoint = ctx.out_point;
            }
            if (q.before_layer_id) { layer.moveBefore(sceneLayer(comp, q.before_layer_id)); }
            if (q.after_layer_id) { layer.moveAfter(sceneLayer(comp, q.after_layer_id)); }
        } else if (action === 'layer_parent') {
            other = q.parent_layer_id ? sceneLayer(comp, q.parent_layer_id) : null;
            if (q.policy === 'preserve_local') { layer.setParentWithJump(other); }
            else { layer.parent = other; }
        } else if (action === 'track_matte_set') {
            other = q.matte_layer_id ? sceneLayer(comp, q.matte_layer_id) : null;
            var wasEnabled = other ? other.enabled : null;
            if (other) { layer.setTrackMatte(other, matteValue(q.mode)); other.enabled = wasEnabled; }
            else { layer.removeTrackMatte(); }
        } else if (action === 'precompose_layers') {
            var indices = [], selected, index;
            for (i = 0; i < q.layer_ids.length; i++) { selected = sceneLayer(comp, q.layer_ids[i]); indices.push(selected.index); }
            indices.sort(function (a, b) { return a - b; });
            other = comp.layers.precompose(indices, q.name, true);
            other.bgColor = comp.bgColor; other.motionBlur = comp.motionBlur; other.shutterAngle = comp.shutterAngle;
            other.comment = 'astra:composition:' + ctx.new_composition_id;
            for (i = 1; i <= other.numLayers; i++) { info.moved_native_ids.push(other.layer(i).id); }
            layer = null;
            for (i = 1; i <= comp.numLayers; i++) { if (comp.layer(i).source && comp.layer(i).source.id == other.id) { layer = comp.layer(i); } }
            if (!layer) { throw new Error('Precomp layer absent'); }
            layer.comment = 'astra:layer:' + ctx.new_layer_id; layer.name = q.name;
        } else { throw new Error('Unknown scene edit'); }
    } finally { app.endUndoGroup(); }
    app.project.save(file);
    if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(file)) { throw new Error('Scene version reopen failed'); }
    return info;
}
