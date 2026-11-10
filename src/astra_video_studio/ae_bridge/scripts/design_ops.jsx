// Controlled native design operations; all editable inputs are JSON data.
function isShape(layer) { if (layer instanceof ShapeLayer) { return true; } return false; }
function plainRect(rect) { return {left: rect.left, top: rect.top, width: rect.width, height: rect.height}; }
function designBounds(layer, time) {
    if (!isEditable2D(layer) || layer.nullLayer) { return null; }
    return plainRect(layer.sourceRectAtTime(time, true));
}
function alignValue(name) {
    if (name === 'left') { return ParagraphJustification.LEFT_JUSTIFY; }
    if (name === 'right') { return ParagraphJustification.RIGHT_JUSTIFY; }
    return ParagraphJustification.CENTER_JUSTIFY;
}
function alignName(value) {
    var names = ['left', 'center', 'right'];
    for (var i = 0; i < names.length; i++) { if (Number(value) - Number(alignValue(names[i])) == 0) { return names[i]; } }
    return String(value);
}
function fontInfo(font) {
    return {postscript_name: font.postScriptName, font_id: font.fontID, family: font.familyName, style: font.styleName, substitute: font.isSubstitute === true};
}
function listDesignFonts(query) {
    var groups = app.fonts.allFonts, fonts = [], count = 0, needle = query.query.toLowerCase(), i, j, f;
    for (i = 0; i < groups.length; i++) {
        for (j = 0; j < groups[i].length; j++) {
            f = groups[i][j];
            if (f.isSubstitute === true || (f.postScriptName + ' ' + f.familyName + ' ' + f.styleName).toLowerCase().indexOf(needle) < 0) { continue; }
            count++; if (fonts.length < query.limit) { fonts.push(fontInfo(f)); }
        }
    }
    return {fonts: fonts, matched_count: count, truncated: count > fonts.length,
        capabilities: {character_ranges: true, box_overflow: true, native_paths: true, text_animators: true,
        svg_import: 'strict native-path subset', gradient_color_editing: false, gradient_limitation: 'No supported gradient color serialization contract in this bridge'}};
}
function resolveDesignFont(selection) {
    var groups = app.fonts.allFonts, matches = [], i, j, f;
    for (i = 0; i < groups.length; i++) {
        for (j = 0; j < groups[i].length; j++) {
            f = groups[i][j];
            if (f.postScriptName === selection.postscript_name && f.isSubstitute !== true && (selection.font_id === null || f.fontID - selection.font_id == 0)) { matches.push(f); }
        }
    }
    if (matches.length !== 1) { throw new Error('FONT_MISSING_OR_AMBIGUOUS: use fonts_list and an exact installed font (font_id is session-specific)'); }
    return matches[0];
}
function characterStyle(doc) {
    var fill = null;
    if (doc.applyFill) { fill = doc.fillColor; }
    return {font: doc.font, font_size: doc.fontSize, tracking: doc.tracking, fill: fill};
}
function designTextStyle(doc) {
    var runs = [], i = 0, point = 0, width, current, previous = null, range, size = null, overflow = false;
    while (i < doc.text.length && point < 500) {
        width = 1;
        if (doc.text.charCodeAt(i) >= 0xD800 && doc.text.charCodeAt(i) <= 0xDBFF && i + 1 < doc.text.length) { width = 2; }
        range = doc.characterRange(i, i + width); current = characterStyle(range);
        if (previous && encode(previous.style) === encode(current)) { previous.end = point + 1; }
        else { previous = {start: point, end: point + 1, style: current}; runs.push(previous); }
        i += width; point++;
    }
    if (doc.boxText) { size = doc.boxTextSize; overflow = doc.boxOverflow; }
    return {font: doc.font, font_size: doc.fontSize, tracking: doc.tracking, all_caps: doc.allCaps,
        font_family: doc.fontFamily, font_style: doc.fontStyle, font_missing: doc.fontObject.isSubstitute === true,
        leading: doc.leading, auto_leading: doc.autoLeading, alignment: alignName(doc.justification),
        fill: characterStyle(doc).fill, box_text: doc.boxText, box_size: size, box_overflow: overflow,
        line_count: doc.composedLineCount, style_runs: runs, styles_truncated: i < doc.text.length};
}
function textDocumentAnimated(layer) {
    if (!(layer instanceof TextLayer)) { return false; }
    var prop = layer.property('ADBE Text Properties').property('ADBE Text Document');
    return prop.numKeys > 0 || prop.expressionEnabled;
}
function groupUUID(name) {
    var match = /\[astra:([0-9a-f]{32})\]$/.exec(name); return match ? match[1] : null;
}
function pathGeometry(shape) { return {vertices: shape.vertices, in_tangents: shape.inTangents, out_tangents: shape.outTangents, closed: shape.closed}; }
function simpleKeys(prop) {
    var keys = []; for (var i = 1; i <= prop.numKeys; i++) { keys.push({time: prop.keyTime(i), value: prop.keyValue(i), in_type: interpolation(prop.keyInInterpolationType(i)), out_type: interpolation(prop.keyOutInterpolationType(i))}); } return keys;
}
function inspectShapeGroups(layer) {
    if (!isShape(layer)) { return []; }
    var root = layer.property('ADBE Root Vectors Group'), groups = [], i, j, group, contents, prop, path, paths, fill, stroke, trim, keys, k, animated;
    for (i = 1; i <= root.numProperties; i++) {
        group = root.property(i);
        if (group.matchName !== 'ADBE Vector Group') { continue; }
        contents = group.property('ADBE Vectors Group'); paths = []; fill = null; stroke = null; trim = null; animated = false;
        for (j = 1; j <= contents.numProperties; j++) {
            prop = contents.property(j);
            if (prop.matchName === 'ADBE Vector Shape - Group') {
                path = prop.property('ADBE Vector Shape'); keys = [];
                for (k = 1; k <= path.numKeys; k++) { keys.push({time: path.keyTime(k), geometry: pathGeometry(path.keyValue(k)), in_type: interpolation(path.keyInInterpolationType(k)), out_type: interpolation(path.keyOutInterpolationType(k))}); }
                paths.push({kind: 'path', geometry: pathGeometry(path.valueAtTime(0, false)), keys: keys});
            } else if (prop.matchName === 'ADBE Vector Shape - Rect') {
                paths.push({kind: 'rectangle', size: prop.property('ADBE Vector Rect Size').valueAtTime(0, false), position: prop.property('ADBE Vector Rect Position').valueAtTime(0, false), roundness: prop.property('ADBE Vector Rect Roundness').valueAtTime(0, false), keys: []});
            } else if (prop.matchName === 'ADBE Vector Shape - Ellipse') {
                paths.push({kind: 'ellipse', size: prop.property('ADBE Vector Ellipse Size').valueAtTime(0, false), position: prop.property('ADBE Vector Ellipse Position').valueAtTime(0, false), keys: []});
            } else if (prop.matchName === 'ADBE Vector Graphic - Fill') {
                fill = {enabled: prop.enabled, color: prop.property('ADBE Vector Fill Color').valueAtTime(0, false).slice(0, 3), opacity: prop.property('ADBE Vector Fill Opacity').valueAtTime(0, false)};
                if (animationSummary(prop).key_count) { animated = true; }
            } else if (prop.matchName === 'ADBE Vector Graphic - Stroke') {
                stroke = {enabled: prop.enabled, color: prop.property('ADBE Vector Stroke Color').valueAtTime(0, false).slice(0, 3), opacity: prop.property('ADBE Vector Stroke Opacity').valueAtTime(0, false), width: prop.property('ADBE Vector Stroke Width').valueAtTime(0, false), cap: prop.property('ADBE Vector Stroke Line Cap').value, join: prop.property('ADBE Vector Stroke Line Join').value};
                if (animationSummary(prop).key_count) { animated = true; }
            } else if (prop.matchName === 'ADBE Vector Filter - Trim') {
                trim = {start: prop.property('ADBE Vector Trim Start').valueAtTime(0, false), end: prop.property('ADBE Vector Trim End').valueAtTime(0, false), offset: prop.property('ADBE Vector Trim Offset').valueAtTime(0, false), end_keys: simpleKeys(prop.property('ADBE Vector Trim End'))};
            }
        }
        groups.push({group_id: groupUUID(group.name), name: group.name, paths: paths, fill: fill, stroke: stroke, trim: trim, style_animated: animated});
    }
    return groups;
}
function inspectTextAnimators(layer) {
    if (!(layer instanceof TextLayer)) { return []; }
    var group = layer.property('ADBE Text Properties').property('ADBE Text Animators'), result = [], i, animator, props, selector, advanced;
    for (i = 1; i <= group.numProperties; i++) {
        animator = group.property(i); props = animator.property('ADBE Text Animator Properties');
        if (!groupUUID(animator.name)) { result.push({name: animator.name, animator_id: null, property_count: props.numProperties}); continue; }
        selector = animator.property('ADBE Text Selectors').property(1); advanced = selector.property('ADBE Text Range Advanced');
        result.push({name: animator.name, animator_id: groupUUID(animator.name), position: props.property('ADBE Text Position 3D').value,
            scale: props.property('ADBE Text Scale 3D').value, opacity: props.property('ADBE Text Opacity').value,
            based_on: advanced.property('ADBE Text Range Type2').value, start_keys: simpleKeys(selector.property('ADBE Text Percent Start'))});
    }
    return result;
}
function designGroup(layer, uuid) {
    var root = layer.property('ADBE Root Vectors Group'), matches = [];
    for (var i = 1; i <= root.numProperties; i++) { if (groupUUID(root.property(i).name) === uuid) { matches.push(root.property(i)); } }
    if (matches.length !== 1) { throw new Error('Managed shape group absent/ambiguous'); } return matches[0];
}
function designContents(layer, uuid) { return designGroup(layer, uuid).property('ADBE Vectors Group'); }
function nativePath(data) {
    var shape = new Shape(); shape.vertices = data.vertices; shape.inTangents = data.in_tangents; shape.outTangents = data.out_tangents; shape.closed = data.closed; return shape;
}
function createDesignPath(layer, item) {
    var root = layer.property('ADBE Root Vectors Group');
    var group = root.addProperty('ADBE Vector Group'); group.name = item.name + ' [astra:' + item.group_id + ']';
    designContents(layer, item.group_id).addProperty('ADBE Vector Shape - Group');
    designContents(layer, item.group_id).property('ADBE Vector Shape - Group').property('ADBE Vector Shape').setValue(nativePath(item.path));
}
function setDesignPaint(layer, uuid, kind, color, enabled, opacity, width) {
    if (color === null && enabled === null && opacity === null && width === null) { return; }
    var match = 'ADBE Vector Graphic - Fill', prefix = 'ADBE Vector Fill';
    if (kind === 'stroke') { match = 'ADBE Vector Graphic - Stroke'; prefix = 'ADBE Vector Stroke'; }
    var content = designContents(layer, uuid), paint = content.property(match);
    if (!paint) {
        content.addProperty(match); paint = designContents(layer, uuid).property(match);
        paint.property(prefix + ' Color').setValue([1, 1, 1, 1]); paint.property(prefix + ' Opacity').setValue(100);
        if (kind === 'stroke') { paint.property('ADBE Vector Stroke Width').setValue(1); paint.property('ADBE Vector Stroke Line Cap').setValue(1); paint.property('ADBE Vector Stroke Line Join').setValue(1); }
    }
    if (color !== null) { paint.property(prefix + ' Color').setValue([color[0], color[1], color[2], 1]); }
    if (enabled !== null) { paint.enabled = enabled; }
    if (opacity !== null) { paint.property(prefix + ' Opacity').setValue(opacity); }
    if (width !== null) { paint.property('ADBE Vector Stroke Width').setValue(width); }
}
function applyCharacterStyle(doc, style) {
    if (style.font !== null) { doc.fontObject = resolveDesignFont(style.font); }
    if (style.font_size !== null) { doc.fontSize = Math.round(style.font_size * 100) / 100; }
    if (style.tracking !== null) { doc.tracking = style.tracking; }
    if (style.fill !== null) { doc.applyFill = true; doc.fillColor = style.fill; }
}
function centerDesignAnchor(layer, comp) {
    var rect = layer.sourceRectAtTime(comp.duration / 2, true);
    transform(layer, 'anchor').setValue([rect.left + rect.width / 2, rect.top + rect.height / 2]);
}
function validateStyleFonts(style) { if (style.font) { resolveDesignFont(style.font); } }
function applyDesignLayout(comp, request, ctx) {
    comp.width = ctx.width; comp.height = ctx.height;
    var prepared = [], i, binding, layer, doc, prop, token, rect, ratio, pos, w, h;
    var safe = ctx.tokens.safe_area, left = safe[0] * comp.width, right = (1 - safe[2]) * comp.width;
    var top = safe[1] * comp.height, bottom = (1 - safe[3]) * comp.height;
    for (i = 0; i < request.bindings.length; i++) {
        binding = request.bindings[i]; layer = sceneLayer(comp, binding.layer_id);
        if (layer instanceof TextLayer) {
            prop = layer.property('ADBE Text Properties').property('ADBE Text Document'); doc = prop.value;
            if (binding.typography_token) {
                token = ctx.tokens.typography[binding.typography_token];
                applyCharacterStyle(doc, {font: token.font, font_size: Math.min(comp.width, comp.height) * token.size_ratio, tracking: token.tracking, fill: ctx.tokens.colors[token.color]});
            }
            if (doc.boxText) { doc.boxTextSize = [binding.max_width * comp.width, binding.max_height * comp.height]; }
            prop.setValue(doc);
            if (prop.value.boxText && prop.value.boxOverflow) { throw new Error('LAYOUT_TEXT_OVERFLOW'); }
        }
        rect = layer.sourceRectAtTime(comp.duration / 2, true);
        if (rect.width <= 0 || rect.height <= 0) { throw new Error('LAYOUT_EMPTY_BOUNDS'); }
        ratio = Math.min(1, binding.max_width * comp.width / rect.width, binding.max_height * comp.height / rect.height);
        pos = [binding.x * comp.width, binding.y * comp.height];
        if (binding.role === 'background') { ratio = Math.max(comp.width / rect.width, comp.height / rect.height); pos = [comp.width / 2, comp.height / 2]; }
        transform(layer, 'anchor').setValue([rect.left + rect.width / 2, rect.top + rect.height / 2]);
        transform(layer, 'scale').setValue([ratio * 100, ratio * 100]);
        w = rect.width * ratio; h = rect.height * ratio;
        prepared.push({layer: layer, binding: binding, width: w, height: h, position: pos});
    }
    var content = [], total = 0, horizontal = request.arrangement === 'distribute_horizontal';
    for (i = 0; i < prepared.length; i++) { if (prepared[i].binding.role !== 'background') { content.push(prepared[i]); total += horizontal ? prepared[i].width : prepared[i].height; } }
    if (request.arrangement === 'distribute_horizontal' || request.arrangement === 'distribute_vertical') {
        var available = horizontal ? right - left : bottom - top;
        var gap = content.length > 1 ? (available - total) / (content.length - 1) : 0;
        if (gap < ctx.tokens.spacing_ratio * Math.min(comp.width, comp.height) && content.length > 1) { throw new Error('LAYOUT_DISTRIBUTION_TOO_DENSE'); }
        var cursor = horizontal ? left : top;
        for (i = 0; i < content.length; i++) { var extent = horizontal ? content[i].width : content[i].height; content[i].position[horizontal ? 0 : 1] = cursor + extent / 2; cursor += extent + gap; }
    }
    for (i = 0; i < prepared.length; i++) {
        var item = prepared[i]; pos = item.position;
        if (item.binding.role !== 'background') {
            if (request.arrangement === 'align_left') { pos[0] = left + item.width / 2; }
            if (request.arrangement === 'align_center') { pos[0] = (left + right) / 2; }
            if (request.arrangement === 'align_right') { pos[0] = right - item.width / 2; }
            if (pos[0] - item.width / 2 < left - 0.01 || pos[0] + item.width / 2 > right + 0.01 || pos[1] - item.height / 2 < top - 0.01 || pos[1] + item.height / 2 > bottom + 0.01) { throw new Error('LAYOUT_SAFE_AREA_VIOLATION'); }
        }
        transform(item.layer, 'position').setValue(pos);
    }
}
function runDesignEdit() {
    var before = inspect(), q = p.request, ctx = p.context, action = p.design_action, comp = sceneComp(q.composition_id), layer, prop, doc, i, group, properties, selector;
    if (app.project.dirty !== false || encode(before.compositions) !== encode(p.expected_state.compositions) || encode(before.footage) !== encode(p.expected_state.footage)) { throw new Error('STATE_CONFLICT'); }
    if (action !== 'layout_apply') { layer = sceneLayer(comp, q.layer_id); }
    // Resolve every requested font before creating a new version; never accept substitution.
    if (action === 'text_style_set') {
        validateStyleFonts(q); for (i = 0; i < q.ranges.length; i++) { validateStyleFonts(q.ranges[i]); }
    }
    if (action === 'layout_apply') {
        for (i = 0; i < q.bindings.length; i++) { if (q.bindings[i].typography_token) { resolveDesignFont(ctx.tokens.typography[q.bindings[i].typography_token].font); } }
    }
    var file = new File(p.version_path);
    if (file.exists) { throw new Error('OUTPUT_EXISTS'); }
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    var originalPath = p.project_path, designFailure = null;
    app.project.save(file); p.project_path = p.version_path;
    app.beginUndoGroup('Astra design ' + action);
    try {
        if (action === 'text_style_set') {
            prop = layer.property('ADBE Text Properties').property('ADBE Text Document'); doc = prop.value;
            applyCharacterStyle(doc, q);
            if (q.leading !== null) { doc.autoLeading = false; doc.leading = q.leading; }
            if (q.alignment !== null) { doc.justification = alignValue(q.alignment); }
            if (q.box_size !== null) { doc.boxTextSize = q.box_size; }
            for (i = 0; i < ctx.native_ranges.length; i++) { var range = ctx.native_ranges[i]; applyCharacterStyle(doc.characterRange(range.start, range.end), range); }
            prop.setValue(doc);
            if (q.overflow_policy === 'reject' && prop.value.boxText && prop.value.boxOverflow) { throw new Error('TEXT_BOX_OVERFLOW'); }
            if (q.recenter_anchor) { centerDesignAnchor(layer, comp); }
        } else if (action === 'text_animator_apply') {
            group = layer.property('ADBE Text Properties').property('ADBE Text Animators').addProperty('ADBE Text Animator');
            group.name = 'Astra entry [astra:' + ctx.animator_id + ']'; var animatorIndex = group.propertyIndex;
            function animator() { return layer.property('ADBE Text Properties').property('ADBE Text Animators').property(animatorIndex); }
            animator().property('ADBE Text Animator Properties').addProperty('ADBE Text Position 3D');
            animator().property('ADBE Text Animator Properties').addProperty('ADBE Text Scale 3D');
            animator().property('ADBE Text Animator Properties').addProperty('ADBE Text Opacity');
            properties = animator().property('ADBE Text Animator Properties');
            properties.property('ADBE Text Position 3D').setValue([q.position[0], q.position[1], 0]);
            properties.property('ADBE Text Scale 3D').setValue([q.scale, q.scale, 100]);
            properties.property('ADBE Text Opacity').setValue(q.opacity);
            animator().property('ADBE Text Selectors').addProperty('ADBE Text Selector');
            selector = animator().property('ADBE Text Selectors').property(1);
            var based = 1; if (q.based_on === 'words') { based = 3; }
            selector.property('ADBE Text Range Advanced').property('ADBE Text Range Type2').setValue(based);
            prop = selector.property('ADBE Text Percent Start'); prop.setValueAtTime(ctx.times[0], 0); prop.setValueAtTime(ctx.times[1], 100);
            for (i = 1; i <= prop.numKeys; i++) { prop.setInterpolationTypeAtKey(i, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR); }
        } else if (action === 'shape_path_set') {
            if (q.group_id === null) { createDesignPath(layer, {group_id: ctx.group_id, name: q.name, path: q.path}); }
            else { designContents(layer, q.group_id).property('ADBE Vector Shape - Group').property('ADBE Vector Shape').setValue(nativePath(q.path)); }
        } else if (action === 'shape_style_set') {
            setDesignPaint(layer, q.group_id, 'fill', q.fill, q.fill_enabled, q.fill_opacity, null);
            setDesignPaint(layer, q.group_id, 'stroke', q.stroke, q.stroke_enabled, q.stroke_opacity, q.stroke_width);
        } else if (action === 'shape_trim_apply') {
            designContents(layer, q.group_id).addProperty('ADBE Vector Filter - Trim');
            group = designContents(layer, q.group_id).property('ADBE Vector Filter - Trim');
            group.property('ADBE Vector Trim Start').setValue(q.start_percent); group.property('ADBE Vector Trim Offset').setValue(q.offset);
            prop = group.property('ADBE Vector Trim End'); prop.setValueAtTime(ctx.times[0], q.start_percent); prop.setValueAtTime(ctx.times[1], q.end_percent);
            for (i = 1; i <= prop.numKeys; i++) { prop.setInterpolationTypeAtKey(i, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR); }
        } else if (action === 'shape_morph_apply') {
            prop = designContents(layer, q.group_id).property('ADBE Vector Shape - Group').property('ADBE Vector Shape');
            prop.setValueAtTime(ctx.times[0], nativePath(ctx.start_path)); prop.setValueAtTime(ctx.times[1], nativePath(q.end_path));
            for (i = 1; i <= prop.numKeys; i++) { prop.setInterpolationTypeAtKey(i, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR); }
        } else if (action === 'vector_import') {
            for (i = 0; i < ctx.groups.length; i++) {
                var item = ctx.groups[i]; createDesignPath(layer, item);
                if (item.fill) { setDesignPaint(layer, item.group_id, 'fill', item.fill.color, true, item.fill.opacity, null); }
                if (item.stroke) { setDesignPaint(layer, item.group_id, 'stroke', item.stroke.color, true, item.stroke.opacity, item.stroke.width); }
            }
        } else if (action === 'layout_apply') { applyDesignLayout(comp, q, ctx); }
        else { throw new Error('Unknown design action'); }
    } catch (error) { designFailure = error; }
    finally { app.endUndoGroup(); }
    if (designFailure) {
        // Known synchronous failure: preserve this job-owned file and restore the
        // clean source checked immediately before mutation. Never retry a timeout.
        app.project.save(file);
        if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(new File(originalPath))) { throw new Error('Design failed; source restore also failed: ' + String(designFailure)); }
        p.project_path = originalPath;
        throw designFailure;
    }
    app.project.save(file);
    if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(file)) { throw new Error('Design reopen failed'); }
}
