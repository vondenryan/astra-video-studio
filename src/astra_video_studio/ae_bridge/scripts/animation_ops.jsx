// Manual native transform-track editing. No expressions or code input.
function animationInterpolation(name) {
    if (name === 'linear') { return KeyframeInterpolationType.LINEAR; }
    if (name === 'bezier') { return KeyframeInterpolationType.BEZIER; }
    if (name === 'hold') { return KeyframeInterpolationType.HOLD; }
    throw new Error('Invalid interpolation');
}
function animationEases(values) {
    var result = [];
    for (var i = 0; i < values.length; i++) { result.push(new KeyframeEase(values[i].speed, values[i].influence)); }
    return result;
}
function replaceManualTrack(layer, name, keys) {
    var prop = transform(layer, name), i, key;
    if (!prop || prop.expressionEnabled || (prop.canSetExpression && prop.expression.length) || (prop.isSeparationLeader && prop.dimensionsSeparated)) { throw new Error('TRACK_PROTECTED'); }
    for (i = prop.numKeys; i >= 1; i--) { prop.removeKey(i); }
    for (i = 0; i < keys.length; i++) { prop.setValueAtTime(keys[i].time, keys[i].value); }
    for (i = 0; i < keys.length; i++) {
        key = keys[i]; var index = i + 1;
        prop.setInterpolationTypeAtKey(index, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
        prop.setTemporalAutoBezierAtKey(index, false); prop.setTemporalContinuousAtKey(index, false);
        prop.setTemporalEaseAtKey(index, animationEases(key.in_ease), animationEases(key.out_ease));
        if (prop.isSpatial) {
            prop.setSpatialAutoBezierAtKey(index, false); prop.setSpatialContinuousAtKey(index, false);
            prop.setSpatialTangentsAtKey(index, key.in_spatial, key.out_spatial);
            prop.setSpatialContinuousAtKey(index, false); prop.setRovingAtKey(index, false);
        }
        prop.setInterpolationTypeAtKey(index, animationInterpolation(key.in_type), animationInterpolation(key.out_type));
    }
}
function runAnimationEdit() {
    var before = inspect(), q = p.request, plan = p.animation_plan;
    if (app.project.dirty !== false || encode(before.compositions) !== encode(p.expected_state.compositions) || encode(before.footage) !== encode(p.expected_state.footage)) { throw new Error('ANIMATION_STATE_CONFLICT'); }
    var comp = sceneComp(q.composition_id), file = new File(p.version_path), original = p.project_path, failure = null, i;
    if (file.exists) { throw new Error('OUTPUT_EXISTS'); }
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    app.project.save(file); p.project_path = p.version_path;
    app.beginUndoGroup('Astra animation ' + p.animation_action);
    try {
        for (i = 0; i < plan.tracks.length; i++) {
            var change = plan.tracks[i], layer = sceneLayer(comp, change.layer_id);
            if (!isEditable2D(layer) || layer.locked) { throw new Error('LAYER_PROTECTED'); }
            replaceManualTrack(layer, change.property, change.keys);
        }
        if (p.animation_action === 'motion_blur_set') {
            comp.motionBlur = q.composition_enabled; comp.shutterAngle = q.shutter_angle; comp.shutterPhase = q.shutter_phase;
            comp.motionBlurSamplesPerFrame = q.samples_per_frame; comp.motionBlurAdaptiveSampleLimit = q.adaptive_sample_limit;
            for (i = 0; i < q.layer_ids.length; i++) { sceneLayer(comp, q.layer_ids[i]).motionBlur = q.layers_enabled; }
        }
    } catch (error) { failure = error; }
    finally { app.endUndoGroup(); }
    app.project.save(file);
    if (failure) {
        if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(new File(original))) { throw new Error('Animation failure and source restore failure: ' + String(failure)); }
        p.project_path = original; throw failure;
    }
    if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(file)) { throw new Error('Animation version reopen failed'); }
}
