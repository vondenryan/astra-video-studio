// Bounded typed patches only. The host preflights and verifies every step.
function runRevisionEdit() {
    var before = inspect();
    if (app.project.dirty !== false || encode(before.compositions) !== encode(p.expected_state.compositions) || encode(before.footage) !== encode(p.expected_state.footage)) { throw new Error('REVISION_STATE_CONFLICT'); }
    var operations = p.revision_operations, i, j, op, q, ctx, comp, layer, prop, doc, name;
    // Resolve fonts before saving or mutating anything.
    for (i = 0; i < operations.length; i++) {
        op = operations[i];
        if (op.action === 'text_style_set') {
            validateStyleFonts(op.request);
            for (j = 0; j < op.request.ranges.length; j++) { validateStyleFonts(op.request.ranges[j]); }
        }
    }
    var file = new File(p.version_path), original = p.project_path, failure = null, steps = [];
    if (file.exists) { throw new Error('OUTPUT_EXISTS'); }
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    app.project.save(file); p.project_path = p.version_path;
    app.beginUndoGroup('Astra revision patch');
    try {
        for (i = 0; i < operations.length; i++) {
            op = operations[i]; q = op.request; ctx = op.context;
            comp = sceneComp(q.composition_id);
            if (op.action === 'animation_retime' || op.action === 'keyframes_edit' || op.action === 'easing_set' || op.action === 'motion_path_set') {
                for (j = 0; j < ctx.tracks.length; j++) {
                    var track = ctx.tracks[j]; layer = sceneLayer(comp, track.layer_id);
                    if (!isEditable2D(layer) || layer.locked) { throw new Error('LAYER_PROTECTED'); }
                    replaceManualTrack(layer, track.property, track.keys);
                }
            } else {
                layer = sceneLayer(comp, q.layer_id);
                if (!isEditable2D(layer) || layer.locked) { throw new Error('LAYER_PROTECTED'); }
                if (op.action === 'content_set') {
                    prop = layer.property('ADBE Text Properties').property('ADBE Text Document');
                    if (prop.numKeys || prop.expressionEnabled || (prop.canSetExpression && prop.expression.length)) { throw new Error('TEXT_PROTECTED'); }
                    doc = prop.value; doc.text = q.text; prop.setValue(doc);
                    if (prop.value.boxText && prop.value.boxOverflow) { throw new Error('TEXT_BOX_OVERFLOW'); }
                } else if (op.action === 'text_style_set') {
                    prop = layer.property('ADBE Text Properties').property('ADBE Text Document'); doc = prop.value;
                    applyCharacterStyle(doc, q);
                    if (q.leading !== null) { doc.autoLeading = false; doc.leading = q.leading; }
                    if (q.alignment !== null) { doc.justification = alignValue(q.alignment); }
                    if (q.box_size !== null) { doc.boxTextSize = q.box_size; }
                    for (j = 0; j < ctx.native_ranges.length; j++) { var range = ctx.native_ranges[j]; applyCharacterStyle(doc.characterRange(range.start, range.end), range); }
                    prop.setValue(doc);
                    if (q.overflow_policy === 'reject' && prop.value.boxText && prop.value.boxOverflow) { throw new Error('TEXT_BOX_OVERFLOW'); }
                    if (q.recenter_anchor) { centerDesignAnchor(layer, comp); }
                } else if (op.action === 'layer_transform') {
                    for (name in q.values) {
                        if (q.values.hasOwnProperty(name) && q.values[name] !== null) {
                            prop = transform(layer, name);
                            if (prop.numKeys || prop.expressionEnabled || (prop.canSetExpression && prop.expression.length) || (prop.isSeparationLeader && prop.dimensionsSeparated)) { throw new Error('TRANSFORM_PROTECTED'); }
                            prop.setValue(adapted(prop, q.values[name] instanceof Array ? q.values[name] : [q.values[name]], name, false));
                        }
                    }
                } else if (op.action === 'layer_update') {
                    layer.startTime = ctx.start_time; layer.inPoint = ctx.in_point; layer.outPoint = ctx.out_point;
                } else { throw new Error('Unknown revision action'); }
            }
            steps.push(inspect());
        }
    } catch (error) { failure = error; }
    finally { app.endUndoGroup(); }
    app.project.save(file);
    if (failure) {
        // Only a confirmed synchronous failure restores a checked-clean source.
        if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(new File(original))) { throw new Error('Revision failed; source restore failed: ' + String(failure)); }
        p.project_path = original; throw failure;
    }
    if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(file)) { throw new Error('Revision reopen failed'); }
    return steps;
}
function runVersionRestore() {
    var before = inspect();
    if (app.project.dirty !== false || encode(before.compositions) !== encode(p.expected_state.compositions) || encode(before.footage) !== encode(p.expected_state.footage)) { throw new Error('RESTORE_STATE_CONFLICT'); }
    var file = new File(p.version_path);
    if (!file.exists || !file.length) { throw new Error('RESTORE_COPY_MISSING'); }
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(file)) { throw new Error('Restore open failed'); }
    p.project_path = p.version_path; p.id_map = p.restore_id_map;
}
