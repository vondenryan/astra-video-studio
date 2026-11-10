// Controlled package inspection/relink/reopen. No commands or arbitrary JSX input.
function deliveryColor() {
    return {bits_per_channel: app.project.bitsPerChannel, working_space: String(app.project.workingSpace),
        linearized: app.project.linearizeWorkingSpace === true};
}
function deliveryInterpretation(item) {
    var src = item.mainSource, value = {is_still: src.isStill === true};
    var names = ['alphaMode', 'invertAlpha', 'premulColor', 'conformFrameRate', 'fieldSeparationType',
        'highQualityFieldSeparation', 'removePulldown', 'loop'], i, v;
    for (i = 0; i < names.length; i++) {
        try { v = src[names[i]]; value[names[i]] = typeof v === 'number' || typeof v === 'boolean' || v instanceof Array ? v : String(v); }
        catch (unavailable) { value[names[i]] = null; }
    }
    value.width = item.width; value.height = item.height; value.duration = item.duration; value.frame_rate = item.frameRate;
    return value;
}
function deliveryHasExpression(group) {
    var i, child;
    if (group.canSetExpression && String(group.expression).length) { return true; }
    if (group.numProperties) {
        for (i = 1; i <= group.numProperties; i++) {
            child = group.property(i);
            if (deliveryHasExpression(child)) { return true; }
        }
    }
    return false;
}
function deliveryDependencies(state) {
    var files = [], unsupported = [], fonts = [], fontNames = {}, plugins = [], pluginNames = {};
    var i, j, k, item, layer, style, names, name, available, groups, f, comp;
    for (i = 1; i <= app.project.numItems; i++) {
        item = app.project.item(i);
        if ((item instanceof FootageItem || item instanceof CompItem) && item.proxySource) { unsupported.push('proxy:' + item.id); }
        if (item instanceof FootageItem && item.file) {
            name = item.file.fsName;
            var suffix = name.toLowerCase().replace(/^.*\./, '');
            var sequence = /^(png|jpg|jpeg|tif|tiff|exr|dpx)$/.test(suffix) && item.mainSource.isStill !== true;
            files.push({ae_id:item.id, path:name, missing:item.footageMissing === true,
                sequence:sequence, interpretation:deliveryInterpretation(item)});
            if (sequence || /^(psd|psb|ai)$/.test(suffix)) { unsupported.push('sequence_or_layered_source:' + item.id); }
        }
        if (!(item instanceof CompItem)) { continue; }
        for (j = 1; j <= item.numLayers; j++) {
            layer = item.layer(j);
            if (deliveryHasExpression(layer)) { unsupported.push('expression_dependency:' + layer.id); }
            if (layer instanceof TextLayer && textDocumentAnimated(layer)) { unsupported.push('animated_source_text:' + layer.id); }
        }
    }
    for (i = 0; i < state.compositions.length; i++) {
        comp = state.compositions[i];
        for (j = 0; j < comp.layers.length; j++) {
            layer = comp.layers[j]; style = layer.text_style;
            if (style) {
                if (style.styles_truncated) { unsupported.push('uninspected_text_styles:' + layer.ae_id); }
                names = [style.font];
                for (k = 0; k < style.style_runs.length; k++) { names.push(style.style_runs[k].style.font); }
                for (k = 0; k < names.length; k++) { if (names[k]) { fontNames[names[k]] = true; } }
            }
            for (k = 0; k < layer.effects.length; k++) {
                name = layer.effects[k].match_name;
                if (!pluginNames[name]) {
                    pluginNames[name] = true;
                    plugins.push({match_name:name, name:layer.effects[k].name,
                        availability:name.indexOf('ADBE ') === 0 ? 'native_dependency' : 'not_verified'});
                    if (name.indexOf('ADBE ') !== 0) { unsupported.push('unverified_plugin:' + name); }
                }
            }
        }
    }
    groups = app.fonts.allFonts;
    for (name in fontNames) {
        if (!fontNames.hasOwnProperty(name)) { continue; }
        available = false;
        for (i = 0; i < groups.length; i++) {
            for (j = 0; j < groups[i].length; j++) {
                f = groups[i][j];
                if (f.postScriptName === name && f.isSubstitute !== true) { available = true; }
            }
        }
        fonts.push({postscript_name:name, available:available, copied:false});
    }
    return {files:files, fonts:fonts, plugins:plugins, unsupported:unsupported, source_color:deliveryColor()};
}
function runDelivery() {
    assertSafeToReplace();
    var restore = app.project && app.project.file ? app.project.file.fsName : null;
    var before, after, dependencies, i, j, item, mapping, found, oldInterpretation;
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    if (app.project && !app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Cannot close safe project'); }
    try {
        if (!app.open(new File(p.project_path))) { throw new Error('Cannot open package/copy'); }
        before = inspect(); dependencies = deliveryDependencies(before);
        if (p.action === 'delivery_collect') {
            if (dependencies.unsupported.length) { throw new Error('Unsupported package dependencies'); }
            for (i = 0; i < p.relinks.length; i++) {
                mapping = p.relinks[i]; found = null;
                for (j = 1; j <= app.project.numItems; j++) {
                    item = app.project.item(j);
                    if (item instanceof FootageItem && item.id - mapping.ae_id == 0) { found = item; break; }
                }
                if (!found || !found.file || normalized(found.file.fsName) !== normalized(mapping.old_path)) {
                    throw new Error('Footage source changed before relink');
                }
                if (!new File(mapping.new_path).exists) { throw new Error('Collected media missing'); }
                oldInterpretation = encode(deliveryInterpretation(found));
                found.replace(new File(mapping.new_path));
                if (encode(deliveryInterpretation(found)) !== oldInterpretation) { throw new Error('Footage interpretation changed'); }
            }
            app.project.save(new File(p.project_path));
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(new File(p.project_path))) {
                throw new Error('Package save/reopen failed');
            }
        }
        after = inspect();
        if (encode(before.compositions) !== encode(after.compositions)) { throw new Error('Package non-target composition/layer state changed'); }
        return {before:before, after:after, dependencies:deliveryDependencies(after), reopened:true};
    } finally {
        if (app.project) { app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES); }
        if (restore) { if (!app.open(new File(restore))) { throw new Error('Cannot restore operator project'); } }
        else { app.newProject(); }
    }
}
