// Trusted Astra Sprint 1 template. ExtendScript / ES3; no eval or arbitrary code input.
(function () {
    var p = /*ASTRA_INPUT*/null;
    function quote(value) {
        return '"' + String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
            .replace(/[\x00-\x1f]/g, function (c) {
                return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
            }) + '"';
    }
    function encode(value) {
        if (value === null || typeof value === 'undefined') { return 'null'; }
        if (typeof value === 'string') { return quote(value); }
        if (typeof value === 'number' || typeof value === 'boolean') { return String(value); }
        var parts = [], i, key;
        if (value instanceof Array) {
            for (i = 0; i < value.length; i++) { parts.push(encode(value[i])); }
            return '[' + parts.join(',') + ']';
        }
        for (key in value) {
            if (value.hasOwnProperty(key)) { parts.push(quote(key) + ':' + encode(value[key])); }
        }
        return '{' + parts.join(',') + '}';
    }
    // SHA-256 over actual file BYTES (including any UTF-8 BOM), not JS UTF-16
    // code units. Chunked ES3 implementation; no shell, eval or external library.
    function nativeResultHash(file) {
        var h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
        var k = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
        function rotate(x, n) { return (x >>> n) | (x << (32 - n)); }
        function block(bytes, offset) {
            var w = [], i, j, a, b, c, d, e, f, g, hh, s0, s1, t1, t2;
            for (i = 0; i < 16; i++) {
                j = offset + i * 4;
                w[i] = ((bytes.charCodeAt(j)&255)<<24) | ((bytes.charCodeAt(j+1)&255)<<16) | ((bytes.charCodeAt(j+2)&255)<<8) | (bytes.charCodeAt(j+3)&255);
            }
            for (i = 16; i < 64; i++) {
                s0 = rotate(w[i-15],7) ^ rotate(w[i-15],18) ^ (w[i-15] >>> 3);
                s1 = rotate(w[i-2],17) ^ rotate(w[i-2],19) ^ (w[i-2] >>> 10);
                w[i] = (w[i-16] + s0 + w[i-7] + s1) | 0;
            }
            a=h[0];b=h[1];c=h[2];d=h[3];e=h[4];f=h[5];g=h[6];hh=h[7];
            for (i = 0; i < 64; i++) {
                s1 = rotate(e,6) ^ rotate(e,11) ^ rotate(e,25);
                t1 = (hh + s1 + ((e&f) ^ ((~e)&g)) + k[i] + w[i]) | 0;
                s0 = rotate(a,2) ^ rotate(a,13) ^ rotate(a,22);
                t2 = (s0 + ((a&b) ^ (a&c) ^ (b&c))) | 0;
                hh=g;g=f;f=e;e=(d+t1)|0;d=c;c=b;b=a;a=(t1+t2)|0;
            }
            h[0]=(h[0]+a)|0;h[1]=(h[1]+b)|0;h[2]=(h[2]+c)|0;h[3]=(h[3]+d)|0;
            h[4]=(h[4]+e)|0;h[5]=(h[5]+f)|0;h[6]=(h[6]+g)|0;h[7]=(h[7]+hh)|0;
        }
        var buffer = '', total = 0, chunk, position, i, high, low, output = '';
        file.encoding = 'BINARY';
        if (!file.open('r')) { throw new Error('RESULT_HASH_READ_FAILED'); }
        try {
            while (!file.eof) {
                chunk = file.read(65536);
                if (!chunk.length && !file.eof) { throw new Error('RESULT_HASH_SHORT_READ'); }
                total += chunk.length; buffer += chunk; position = 0;
                while (position + 64 <= buffer.length) { block(buffer, position); position += 64; }
                buffer = buffer.substring(position);
            }
        } finally { file.close(); }
        if (total !== file.length) { throw new Error('RESULT_HASH_LENGTH_CHANGED'); }
        high = Math.floor(total / 536870912); low = (total * 8) >>> 0;
        buffer += String.fromCharCode(128);
        while (buffer.length % 64 !== 56) { buffer += String.fromCharCode(0); }
        for (i = 3; i >= 0; i--) { buffer += String.fromCharCode((high >>> (i*8)) & 255); }
        for (i = 3; i >= 0; i--) { buffer += String.fromCharCode((low >>> (i*8)) & 255); }
        for (position = 0; position < buffer.length; position += 64) { block(buffer, position); }
        for (i = 0; i < 8; i++) { output += ('00000000' + (h[i] >>> 0).toString(16)).slice(-8); }
        return output;
    }
    function publishNativeResult(value) {
        var directory = new File(p.result_path).parent;
        var temporary = new File(directory.fsName + '/native-result.incomplete.json');
        var destination = new File(directory.fsName + '/native-result.json');
        if (temporary.exists || destination.exists) { throw new Error('RESULT_ARTIFACT_EXISTS'); }
        temporary.encoding = 'UTF-8';
        if (!temporary.open('w')) { throw new Error('RESULT_ARTIFACT_OPEN_FAILED'); }
        var written = false;
        try { written = temporary.write(encode({schema_version:1, protocol:'artifact-v1', result:value})); }
        finally { temporary.close(); }
        if (!written || !temporary.length || temporary.length > 16777216) { throw new Error('RESULT_ARTIFACT_SIZE_OR_WRITE_FAILED: ' + temporary.length); }
        var bytes = temporary.length, hash = nativeResultHash(temporary);
        if (destination.exists || !temporary.rename('native-result.json')) { throw new Error('RESULT_ARTIFACT_PUBLISH_FAILED'); }
        if (!destination.exists || destination.length !== bytes) { throw new Error('RESULT_ARTIFACT_PUBLISH_LENGTH_CHANGED'); }
        return {operation_id:p.operation_id, status:value.status, protocol:'artifact-v1', evidence:{file:'native-result.json', bytes:bytes, sha256:hash}};
    }
    function normalized(path) { return new File(path).fsName.toLowerCase(); }
    function identity(kind, object) {
        var group = kind === 'composition' ? 'compositions' : 'layers';
        if (p.id_map && p.id_map[group] && p.id_map[group][String(object.id)]) {
            return 'astra:' + kind + ':' + p.id_map[group][String(object.id)];
        }
        return object.comment;
    }
    function staticValue(layer, name) {
        var prop = transform(layer, name);
        return prop ? prop.valueAtTime(p.sample_time || 0, false) : null;
    }
    var properties = {position: 'ADBE Position', anchor: 'ADBE Anchor Point', scale: 'ADBE Scale', rotation: 'ADBE Rotate Z', opacity: 'ADBE Opacity'};
    function transform(layer, name) { return layer.property('ADBE Transform Group').property(properties[name]); }
    function isEditable2D(layer) {
        // Host instanceof does not reliably expose inheritance (TextLayer may
        // not be instanceof AVLayer). Inspect concrete type/capabilities instead.
        return !layer.threeDLayer && !(layer instanceof CameraLayer) && !(layer instanceof LightLayer)
            && !!transform(layer, 'position') && !!transform(layer, 'anchor') && !!transform(layer, 'scale')
            && !!transform(layer, 'rotation') && !!transform(layer, 'opacity');
    }
    function addLayer(comp, spec, uuid, nativeAsset) {
        var layer, path, fill, contents, group;
        if (spec.kind === 'text') {
            if (spec.text_box) {
                layer = comp.layers.addBoxText(spec.text_box, spec.text);
            } else { layer = comp.layers.addText(spec.text); }
            var property = layer.property('ADBE Text Properties').property('ADBE Text Document'), doc = property.value;
            doc.resetCharStyle(); doc.resetParagraphStyle();
            doc.fontCapsOption = FontCapsOption.FONT_NORMAL_CAPS;
            doc.fontBaselineOption = FontBaselineOption.FONT_NORMAL_BASELINE;
            doc.font = 'Arial-BoldMT'; doc.fontSize = spec.font_size; doc.tracking = spec.tracking;
            doc.applyFill = true; doc.fillColor = spec.color; doc.applyStroke = false; doc.justification = ParagraphJustification.CENTER_JUSTIFY;
            property.setValue(doc);
            var rect = layer.sourceRectAtTime(0, false), fit = Math.min(1, comp.width * 0.86 / Math.max(1, rect.width));
            if (fit < 1 && !spec.text_box) { doc = property.value; doc.fontSize = doc.fontSize * fit; property.setValue(doc); rect = layer.sourceRectAtTime(0, false); }
            transform(layer, 'anchor').setValue([rect.left + rect.width / 2, rect.top + rect.height / 2]);
        } else if (spec.kind === 'shape') {
            layer = comp.layers.addShape();
            if (spec.shape !== 'empty') {
            group = layer.property('ADBE Root Vectors Group').addProperty('ADBE Vector Group');
            contents = group.property('ADBE Vectors Group');
            if (spec.shape === 'ellipse') {
                path = contents.addProperty('ADBE Vector Shape - Ellipse'); path.property('ADBE Vector Ellipse Size').setValue(spec.size);
            } else {
                path = contents.addProperty('ADBE Vector Shape - Rect'); path.property('ADBE Vector Rect Size').setValue(spec.size);
            }
            fill = contents.addProperty('ADBE Vector Graphic - Fill'); fill.property('ADBE Vector Fill Color').setValue([spec.color[0],spec.color[1],spec.color[2],1]);
            }
        } else if (spec.kind === 'solid') {
            layer = comp.layers.addSolid(spec.color, spec.name, Math.round(spec.size[0]), Math.round(spec.size[1]), 1, comp.duration);
        } else {
            var asset = null;
            for (var ai = 1; ai <= app.project.numItems; ai++) { if (app.project.item(ai).id == nativeAsset) { asset = app.project.item(ai); } }
            if (!asset || !(asset instanceof FootageItem)) { throw new Error('Imported asset absent'); }
            layer = comp.layers.add(asset);
        }
        layer.name = spec.name; layer.comment = 'astra:layer:' + uuid;
        transform(layer, 'position').setValue(spec.position || [comp.width / 2, comp.height / 2]);
        transform(layer, 'opacity').setValue(spec.opacity);
        layer.inPoint = spec.in_point; layer.outPoint = spec.out_point === null ? comp.duration : spec.out_point;
        return layer;
    }
    function interpolation(value) {
        // ExtendScript host enum objects do not have reliable strict identity.
        var nativeValue = String(value);
        if (nativeValue === String(KeyframeInterpolationType.BEZIER)) { return 'bezier'; }
        if (nativeValue === String(KeyframeInterpolationType.HOLD)) { return 'hold'; }
        if (nativeValue === String(KeyframeInterpolationType.LINEAR)) { return 'linear'; }
        throw new Error('UNKNOWN_INTERPOLATION: ' + nativeValue);
    }
    function easeInfo(eases) {
        var values = [], i;
        for (i = 0; i < eases.length; i++) { values.push({speed: eases[i].speed, influence: eases[i].influence}); }
        return values;
    }
    function inspectTransforms(layer, duration, fps) {
        var state = {}, name, prop, keys, i, samples, times, j;
        for (name in properties) {
            if (!properties.hasOwnProperty(name)) { continue; }
            prop = transform(layer, name); keys = [];
            if (!prop) { state[name] = {available: false, value: null, keys: [], samples: [], expression_enabled: false, separated: false}; continue; }
            for (i = 1; i <= prop.numKeys; i++) {
                keys.push({time: prop.keyTime(i), value: prop.keyValue(i),
                    in_type: interpolation(prop.keyInInterpolationType(i)), out_type: interpolation(prop.keyOutInterpolationType(i)),
                    in_native: String(prop.keyInInterpolationType(i)), out_native: String(prop.keyOutInterpolationType(i)),
                    in_ease: easeInfo(prop.keyInTemporalEase(i)), out_ease: easeInfo(prop.keyOutTemporalEase(i)),
                    temporal_auto: prop.keyTemporalAutoBezier(i), temporal_continuous: prop.keyTemporalContinuous(i),
                    in_spatial: prop.isSpatial ? prop.keyInSpatialTangent(i) : null, out_spatial: prop.isSpatial ? prop.keyOutSpatialTangent(i) : null,
                    spatial_auto: prop.isSpatial ? prop.keySpatialAutoBezier(i) : false,
                    spatial_continuous: prop.isSpatial ? prop.keySpatialContinuous(i) : false, roving: prop.isSpatial ? prop.keyRoving(i) : false});
            }
            times = [0, duration * 0.25, duration * 0.5, duration * 0.75, Math.max(0, duration - 1 / fps)];
            if (p.sample_times) { for (j = 0; j < p.sample_times.length; j++) { times.push(p.sample_times[j]); } }
            samples = [];
            for (j = 0; j < times.length; j++) { samples.push({time: times[j], value: prop.valueAtTime(times[j], false)}); }
            state[name] = {available: true, value: prop.valueAtTime(0, false), expression_enabled: prop.expressionEnabled === true,
                separated: prop.isSeparationLeader === true && prop.dimensionsSeparated === true, spatial: prop.isSpatial,
                expression_present: prop.canSetExpression && prop.expression.length > 0, keys: keys, samples: samples};
        }
        return state;
    }
    function inspectEffects(layer) {
        var group = layer.property('ADBE Effect Parade'), result = [], i, effect, params;
        if (!group) { return result; }
        for (i = 1; i <= group.numProperties; i++) {
            effect = group.property(i); params = {};
            if (effect.matchName === 'ADBE Gaussian Blur 2') {
                params = {amount: effect.property('ADBE Gaussian Blur 2-0001').value,
                    repeat_edges: effect.property('ADBE Gaussian Blur 2-0003').value};
            } else if (effect.matchName === 'ADBE Fill') { params = {color: effect.property('ADBE Fill-0002').value}; }
            result.push({name: effect.name, match_name: effect.matchName, enabled: effect.enabled, parameters: params, property_count: effect.numProperties});
        }
        return result;
    }
    function inspectMasks(layer) {
        var group = layer.property('ADBE Mask Parade'), result = [], i, mask, shape, nativeMode, modeText;
        var addMode = Number(MaskMode.ADD), subtractMode = Number(MaskMode.SUBTRACT);
        if (!group) { return result; }
        for (i = 1; i <= group.numProperties; i++) {
            mask = group.property(i); shape = mask.property('ADBE Mask Shape').valueAtTime(0, false);
            nativeMode = Number(mask.maskMode);
            modeText = String(nativeMode);
            if (nativeMode - addMode == 0) { modeText = 'add'; }
            else if (nativeMode - subtractMode == 0) { modeText = 'subtract'; }
            var pathKeys = [], pathProperty = mask.property('ADBE Mask Shape'), pk, keyShape;
            for (pk = 1; pk <= pathProperty.numKeys; pk++) {
                keyShape = pathProperty.keyValue(pk);
                pathKeys.push({time: pathProperty.keyTime(pk), vertices: keyShape.vertices,
                    in_type: interpolation(pathProperty.keyInInterpolationType(pk)), out_type: interpolation(pathProperty.keyOutInterpolationType(pk))});
            }
            result.push({name: mask.name, mode: modeText, path_keys: pathKeys,
                native_mode: String(nativeMode), mode_add_value: addMode, mode_subtract_value: subtractMode,
                inverted: mask.inverted, opacity: mask.property('ADBE Mask Opacity').valueAtTime(0, false),
                feather: mask.property('ADBE Mask Feather').valueAtTime(0, false),
                path: {vertices: shape.vertices, in_tangents: shape.inTangents, out_tangents: shape.outTangents, closed: shape.closed}});
        }
        return result;
    }
    function findTarget() {
        var comp = null, layer = null, item, i, j, compCount = 0, layerCount = 0;
        for (i = 1; i <= app.project.numItems; i++) {
            item = app.project.item(i);
            if (item instanceof CompItem && identity('composition', item) === 'astra:composition:' + p.composition_id) { comp = item; compCount++; }
        }
        if (compCount !== 1) { throw new Error('TARGET_NOT_UNIQUE: composition'); }
        for (j = 1; j <= comp.numLayers; j++) {
            if (identity('layer', comp.layer(j)) === 'astra:layer:' + p.layer_id) { layer = comp.layer(j); layerCount++; }
        }
        if (layerCount !== 1 || !isEditable2D(layer) || layer.locked) { throw new Error('TARGET_NOT_UNIQUE_OR_NOT_EDITABLE_2D: layer'); }
        return {comp: comp, layer: layer};
    }
    function adapted(prop, values, name, speed) {
        var size = speed && prop.isSpatial ? 1 : typeof prop.value === 'number' ? 1 : prop.value.length;
        var data = [], i;
        for (i = 0; i < size; i++) { data.push(i < values.length ? values[i] : (!speed && name === 'scale' ? 100 : 0)); }
        return size === 1 && !speed ? data[0] : data;
    }
    function applyMotion(target) {
        var tracks = p.plan.tracks, i, j, prop, keys, key, idx, incoming, outgoing, k, inSpeeds, outSpeeds;
        for (i = 0; i < tracks.length; i++) {
            prop = transform(target.layer, tracks[i].property); keys = tracks[i].keys;
            for (j = 0; j < keys.length; j++) {
                key = keys[j]; prop.setValueAtTime(key.time, adapted(prop, key.value, tracks[i].property, false));
            }
            for (j = 0; j < keys.length; j++) {
                key = keys[j]; idx = prop.nearestKeyIndex(key.time);
                if (prop.isSpatial) {
                    prop.setSpatialAutoBezierAtKey(idx, false); prop.setSpatialContinuousAtKey(idx, false);
                    var zeros = prop.value.length === 3 ? [0, 0, 0] : [0, 0];
                    prop.setSpatialTangentsAtKey(idx, zeros, zeros); prop.setRovingAtKey(idx, false);
                }
                if (key.in_type === 'bezier' || key.out_type === 'bezier') {
                    prop.setInterpolationTypeAtKey(idx, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
                    prop.setTemporalAutoBezierAtKey(idx, false); prop.setTemporalContinuousAtKey(idx, false);
                    inSpeeds = adapted(prop, key.in_speed, tracks[i].property, true);
                    outSpeeds = adapted(prop, key.out_speed, tracks[i].property, true);
                    incoming = []; outgoing = [];
                    for (k = 0; k < inSpeeds.length; k++) {
                        incoming.push(new KeyframeEase(inSpeeds[k], 100 / 3)); outgoing.push(new KeyframeEase(outSpeeds[k], 100 / 3));
                    }
                    prop.setTemporalEaseAtKey(idx, incoming, outgoing);
                }
                prop.setInterpolationTypeAtKey(idx, key.in_type === 'bezier' ? KeyframeInterpolationType.BEZIER : KeyframeInterpolationType.LINEAR,
                    key.out_type === 'bezier' ? KeyframeInterpolationType.BEZIER : KeyframeInterpolationType.LINEAR);
            }
        }
        if (p.plan.mask_reveal) {
            var reveal = target.layer.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');
            reveal.name = 'Astra reveal [' + p.operation_id + ']'; reveal.maskMode = MaskMode.ADD;
            var revealPath = reveal.property('ADBE Mask Shape');
            for (j = 0; j < p.plan.mask_reveal.keys.length; j++) {
                var revealKey = p.plan.mask_reveal.keys[j], shape = new Shape();
                shape.vertices = revealKey.vertices; shape.closed = true;
                shape.inTangents = [[0,0],[0,0],[0,0],[0,0]]; shape.outTangents = [[0,0],[0,0],[0,0],[0,0]];
                revealPath.setValueAtTime(revealKey.time, shape);
            }
            for (j = 1; j <= revealPath.numKeys; j++) { revealPath.setInterpolationTypeAtKey(j, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR); }
        }
        if (p.plan.motion_blur) { target.comp.motionBlur = true; target.comp.shutterAngle = 180; target.layer.motionBlur = true; }
    }
    function preflightEdit(target) {
        var name, prop, i, keys, first, last;
        if (app.project.dirty !== false) { throw new Error('ACTIVE_PROJECT_PROTECTED: unsaved edits'); }
        if (p.action === 'transform') {
            for (name in p.values) {
                if (!p.values.hasOwnProperty(name)) { continue; }
                prop = transform(target.layer, name);
                if (!prop || prop.numKeys || prop.expressionEnabled || (prop.isSeparationLeader && prop.dimensionsSeparated)) { throw new Error('ANIMATED_PROPERTY_PROTECTED: ' + name); }
            }
        } else {
            if (p.plan.start_time < target.layer.inPoint - 0.00001 || p.plan.end_time > Math.min(target.comp.duration, target.layer.outPoint) + 0.00001) { throw new Error('INVALID_TIMELINE'); }
            for (i = 0; i < p.plan.tracks.length; i++) {
                name = p.plan.tracks[i].property; prop = transform(target.layer, name); keys = p.plan.tracks[i].keys;
                if (!prop || prop.expressionEnabled || (prop.isSeparationLeader && prop.dimensionsSeparated) || (prop.numKeys && !(keys[keys.length - 1].time < prop.keyTime(1) - 0.00001 || keys[0].time > prop.keyTime(prop.numKeys) + 0.00001))) {
                    throw new Error('ANIMATION_OVERLAP_OR_EXPRESSION: ' + name);
                }
            }
        }
    }
    function assertSafeToReplace() {
        if (!app.project) { return; }
        // Empty untitled projects are allowed, including AE's startup project.
        if (!app.project.file && app.project.numItems === 0) { return; }
        if (p.source_path && app.project.file && normalized(app.project.file.fsName) === normalized(p.source_path) && app.project.dirty === false) { return; }
        var known = false, i;
        if (app.project.file) {
            for (i = 0; i < p.managed_paths.length; i++) {
                if (normalized(app.project.file.fsName) === normalized(p.managed_paths[i])) { known = true; }
            }
        }
        // Fail closed if the dirty flag is unavailable; never dismiss a save prompt.
        if (!known || app.project.dirty !== false) {
            throw new Error('ACTIVE_PROJECT_PROTECTED: save/close the current project manually. Only unchanged Astra-managed projects may be replaced.');
        }
    }
    function inspect() {
        if (!app.project || !app.project.file || normalized(app.project.file.fsName) !== normalized(p.project_path)) {
            throw new Error('PROJECT_NOT_ACTIVE: the requested project must already be open.');
        }
        var comps = [], footage = [], item, layer, layers, text, rect, textStyle, i, j;
        for (i = 1; i <= app.project.numItems; i++) {
            item = app.project.item(i);
            if (item instanceof FootageItem && item.file) {
                footage.push({ae_id: item.id, name: item.name, path: item.file.fsName, missing: item.footageMissing === true});
            }
            if (!(item instanceof CompItem)) { continue; }
            layers = [];
            for (j = 1; j <= item.numLayers; j++) {
                layer = item.layer(j);
                text = null; rect = null; textStyle = null;
                if (layer instanceof TextLayer) {
                    var inspectedText = layer.property('ADBE Text Properties').property('ADBE Text Document').value;
                    text = inspectedText.text;
                    textStyle = designTextStyle(inspectedText);
                    rect = layer.sourceRectAtTime(0, false);
                    rect = {left: rect.left, top: rect.top, width: rect.width, height: rect.height};
                }
                layers.push({layer_id: identity('layer', layer), ae_id: layer.id, name: layer.name, comment: layer.comment,
                    text: text, text_style: textStyle, bounds: rect,
                    position: staticValue(layer, 'position'),
                    anchor: staticValue(layer, 'anchor'),
                    transforms: inspectTransforms(layer, item.duration, item.frameRate), effects: inspectEffects(layer), masks: inspectMasks(layer), motion_blur: layer.motionBlur,
                    in_point: layer.inPoint, out_point: layer.outPoint,
                    locked: layer.locked, enabled: layer.enabled, three_d: layer.threeDLayer === true,
                    editable_2d: isEditable2D(layer),
                    parent_ae_id: layer.parent ? layer.parent.id : null,
                    source_ae_id: layer.source ? layer.source.id : null,
                    source_kind: sourceKind(layer),
                    source_has_motion: sourceHasMotion(layer),
                    is_null: layer.nullLayer === true,
                    matte_api: typeof layer.setTrackMatte === 'function',
                    matte_ae_id: layer.hasTrackMatte && layer.trackMatteLayer ? layer.trackMatteLayer.id : null,
                    matte_mode: matteName(layer), blend_mode: blendName(layer.blendingMode),
                    animation_summary: animationSummary(layer), world_basis: p.include_world ? worldBasis(layer) : null,
                    auto_orient_none: Number(layer.autoOrient) - Number(AutoOrientType.NO_AUTO_ORIENT) == 0,
                    start_time: layer.startTime, stretch: layer.stretch,
                    is_shape: isShape(layer), shape_groups: inspectShapeGroups(layer), text_animators: inspectTextAnimators(layer),
                    text_document_animated: textDocumentAnimated(layer), visual_bounds: designBounds(layer, 0), layout_bounds: designBounds(layer, item.duration / 2)});
            }
            comps.push({composition_id: identity('composition', item), ae_id: item.id, name: item.name, comment: item.comment,
                width: item.width, height: item.height, fps: item.frameRate,
                duration: item.duration, background: item.bgColor, motion_blur: item.motionBlur, shutter_angle: item.shutterAngle,
                shutter_phase: item.shutterPhase, blur_samples: item.motionBlurSamplesPerFrame, blur_adaptive_limit: item.motionBlurAdaptiveSampleLimit, layers: layers});
        }
        return {project_path: app.project.file.fsName, ae_version: app.version, project_dirty: app.project.dirty, compositions: comps, footage: footage,
            mask_mode_constants: {add: String(MaskMode.ADD), subtract: String(MaskMode.SUBTRACT), none: String(MaskMode.NONE)},
            interpolation_constants: {bezier: String(KeyframeInterpolationType.BEZIER), hold: String(KeyframeInterpolationType.HOLD), linear: String(KeyframeInterpolationType.LINEAR)},
            scene_capabilities: {blend_modes: ['normal', 'multiply', 'screen', 'add'], track_matte_api_version: 23, precompose_move_all_attributes: true}};
    }
    /*ASTRA_SCENE_OPERATIONS*/
    /*ASTRA_DESIGN_OPERATIONS*/
    /*ASTRA_LAYER_BATCH_OPERATIONS*/
    /*ASTRA_ANIMATION_OPERATIONS*/
    /*ASTRA_REVISION_OPERATIONS*/
    /*ASTRA_DELIVERY_OPERATIONS*/
    var result = {operation_id: p.operation_id, status: 'failed', data: {}, error: null};
    var output = new File(p.result_path);
    output.encoding = 'UTF-8';
    // Verify file-write permission BEFORE any project operation.
    if (!output.open('w')) { return; }
    output.close();
    try {
        if (new File(p.cancel_path).exists) { throw new Error('CANCELLED: submission timed out before execution.'); }
        if (String(app.version).split('.')[0] !== '25') { throw new Error('AE_VERSION_UNSUPPORTED'); }
        var importedAsset = null;
        var sceneEditInfo = null;
        var deliveryInfo = null;
        if (p.action === 'delivery_inspect' || p.action === 'delivery_collect' || p.action === 'delivery_validate') { deliveryInfo = runDelivery(); }
        if (p.action === 'scene_edit') { sceneEditInfo = runSceneEdit(); }
        if (p.action === 'design_edit') { runDesignEdit(); }
        if (p.action === 'layers_add') { runLayerBatch(); }
        if (p.action === 'animation_edit') { runAnimationEdit(); }
        var revisionSteps = null;
        if (p.action === 'revision_edit') { revisionSteps = runRevisionEdit(); }
        if (p.action === 'version_restore') { runVersionRestore(); }
        if (p.action === 'layer_add' || p.action === 'asset_import') {
            inspect();
            if (app.project.dirty !== false) { throw new Error('ACTIVE_PROJECT_PROTECTED'); }
            var additionFile = new File(p.version_path);
            if (additionFile.exists) { throw new Error('OUTPUT_EXISTS'); }
            var additionComp = null;
            if (p.action === 'layer_add') {
                for (var ci = 1; ci <= app.project.numItems; ci++) {
                    var ciItem = app.project.item(ci);
                    if (ciItem instanceof CompItem && identity('composition', ciItem) === 'astra:composition:' + p.composition_id) {
                        if (additionComp) { throw new Error('Ambiguous composition'); } additionComp = ciItem;
                    }
                }
                if (!additionComp) { throw new Error('Composition absent'); }
            }
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            app.project.save(additionFile); p.project_path = p.version_path;
            if (p.action === 'asset_import') {
                var imported = app.project.importFile(new ImportOptions(new File(p.asset_path)));
                imported.comment = 'astra:asset:' + p.asset_id;
                importedAsset = {ae_id: imported.id, name: imported.name, width: imported.width, height: imported.height, duration: imported.duration, fps: imported.frameRate};
            } else { addLayer(additionComp, p.layer_spec, p.layer_id, p.native_asset); }
            app.project.save(additionFile);
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(additionFile)) { throw new Error('Layer/import reopen failed'); }
        }
        if (p.action === 'storyboard_build') {
            var sb = p.storyboard, sbFile = new File(p.output_path), sbFonts = {}, sbRole;
            if (sbFile.exists) { throw new Error('OUTPUT_EXISTS'); }
            // Resolve exact installed fonts before replacing a checked-clean project.
            for (sbRole in sb.tokens.typography) {
                if (sb.tokens.typography.hasOwnProperty(sbRole)) {
                    sbFonts[sbRole] = resolveDesignFont(sb.tokens.typography[sbRole].font);
                }
            }
            assertSafeToReplace();
            if (app.project && !app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Protected project'); }
            if (!app.newProject()) { throw new Error('Storyboard creation cancelled'); }
            p.project_path = p.output_path;
            var sbMaster = app.project.items.addComp('Astra Storyboard', sb.brief.width, sb.brief.height, 1, sb.brief.duration_seconds, sb.brief.fps);
            sbMaster.comment = 'astra:composition:' + sb.composition_id;
            sbMaster.bgColor = sb.tokens.colors.background;
            for (var sbi = 0; sbi < sb.scenes.length; sbi++) {
                var sbScene = sb.scenes[sbi];
                var sbComp = app.project.items.addComp('Scene ' + (sbi + 1) + ' / ' + sbScene.card.layout, sb.brief.width, sb.brief.height, 1, sbScene.duration, sb.brief.fps);
                sbComp.comment = 'astra:composition:' + sbScene.composition_id;
                for (var sbe = 0; sbe < sbScene.elements.length; sbe++) {
                    var sbElement = sbScene.elements[sbe];
                    var sbLayer = addLayer(sbComp, sbElement.layer, sbElement.layer_id, null);
                    if (sbElement.layer.kind === 'text') {
                        var sbProp = sbLayer.property('ADBE Text Properties').property('ADBE Text Document');
                        var sbDoc = sbProp.value;
                        sbDoc.fontObject = sbFonts[sbElement.role === 'kicker' ? 'body' : sbElement.role];
                        var sbCentered = sbScene.card.layout === 'hero' || sbElement.role === 'kicker';
                        sbDoc.justification = sbCentered ? ParagraphJustification.CENTER_JUSTIFY : ParagraphJustification.LEFT_JUSTIFY;
                        sbProp.setValue(sbDoc);
                        if (sbProp.value.boxOverflow === true) { throw new Error('STORYBOARD_TEXT_OVERFLOW'); }
                        var sbRect = sbLayer.sourceRectAtTime(0, false);
                        transform(sbLayer, 'anchor').setValue([sbRect.left + (sbCentered ? sbRect.width / 2 : 0), sbRect.top + sbRect.height / 2]);
                    }
                }
                var sbNested = sbMaster.layers.add(sbComp);
                sbNested.name = 'Scene ' + (sbi + 1); sbNested.comment = 'astra:layer:' + sbScene.master_layer_id;
                sbNested.startTime = sbScene.start_frame / sb.brief.fps;
                sbNested.inPoint = sbScene.start_frame / sb.brief.fps;
                sbNested.outPoint = sbScene.end_frame / sb.brief.fps;
            }
            app.project.save(sbFile);
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(sbFile)) { throw new Error('Storyboard reopen failed'); }
        }
        if (p.action === 'scene_build') {
            var sceneFile = new File(p.output_path);
            if (sceneFile.exists) { throw new Error('OUTPUT_EXISTS'); }
            if (p.rebuilding) {
                inspect();
                if (app.project.dirty !== false || app.project.numItems !== 1 || app.project.item(1).comment !== 'astra:composition:' + p.scene.composition_id) { throw new Error('Scene source changed/protected'); }
                app.project.save(sceneFile);
                app.project.item(1).remove(); // Disposable new version only; source retained.
            } else {
                assertSafeToReplace();
                if (app.project && !app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Protected project'); }
                if (!app.newProject()) { throw new Error('Scene creation cancelled'); }
            }
            p.project_path = p.output_path;
            var sceneComp = app.project.items.addComp('Astra Directed Motion', p.scene.width, p.scene.height, 1, p.scene.duration, p.scene.fps);
            sceneComp.comment = 'astra:composition:' + p.scene.composition_id; sceneComp.bgColor = p.scene.background;
            for (var si = 0; si < p.scene.elements.length; si++) {
                var element = p.scene.elements[si]; addLayer(sceneComp, element.layer, element.layer_id, null);
            }
            app.project.save(sceneFile);
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(sceneFile)) { throw new Error('Scene reopen failed'); }
        }
        if (p.action === 'batch_motion') {
            inspect();
            for (var bi = 0; bi < p.motions.length; bi++) {
                p.composition_id = p.motions[bi].composition_id; p.layer_id = p.motions[bi].layer_id; p.plan = p.motions[bi].plan;
                preflightEdit(findTarget());
            }
            var batchFile = new File(p.version_path);
            if (batchFile.exists) { throw new Error('OUTPUT_EXISTS'); }
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            app.project.save(batchFile); p.project_path = p.version_path;
            app.beginUndoGroup('Astra batch motion');
            try {
                for (bi = 0; bi < p.motions.length; bi++) {
                    p.composition_id = p.motions[bi].composition_id; p.layer_id = p.motions[bi].layer_id; p.plan = p.motions[bi].plan;
                    applyMotion(findTarget());
                }
            } finally { app.endUndoGroup(); }
            app.project.save(batchFile);
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(batchFile)) { throw new Error('Batch reopen failed'); }
        }
        var previewInfo = null;
        if (p.action === 'preview_prepare') {
            assertSafeToReplace();
            var restorePath = app.project && app.project.file ? app.project.file.fsName : null;
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            if (app.project && !app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Could not close safe project'); }
            try {
                if (!app.open(new File(p.project_path))) { throw new Error('Could not open isolated render copy'); }
                var renderComp = null, renderMatches = 0, ri;
                for (ri = 1; ri <= app.project.numItems; ri++) {
                    var candidateComp = app.project.item(ri);
                    if (candidateComp instanceof CompItem && identity('composition', candidateComp) === 'astra:composition:' + p.composition_id) { renderComp = candidateComp; renderMatches++; }
                }
                if (renderMatches !== 1) { throw new Error('Preview composition absent/ambiguous'); }
                var queue = app.project.renderQueue;
                while (queue.numItems) { queue.item(1).remove(); } // Only the disposable copy.
                var queued = queue.items.add(renderComp);
                queued.timeSpanStart = p.plan.start_time; queued.timeSpanDuration = p.plan.duration;
                queued.skipFrames = 0;
                var module = queued.outputModule(1), templates = module.templates, templateFound = false;
                var selectedTemplate = p.output_template, selectedPattern = p.frame_pattern;
                if (p.plan.preset === 'tiff_rgba8') {
                    selectedTemplate = 'TIFF Sequence with Alpha'; selectedPattern = p.frame_pattern.replace(/\.png$/i, '.tif');
                }
                for (ri = 0; ri < templates.length; ri++) { if (String(templates[ri]) === selectedTemplate) { templateFound = true; } }
                if (!templateFound && selectedTemplate === 'PNG Sequence') {
                    for (ri = 0; ri < templates.length; ri++) {
                        if (String(templates[ri]) === 'TIFF Sequence with Alpha') {
                            selectedTemplate = 'TIFF Sequence with Alpha'; selectedPattern = p.frame_pattern.replace(/\.png$/i, '.tif'); templateFound = true;
                        }
                    }
                }
                if (!templateFound) { throw new Error('PNG_TEMPLATE_NOT_FOUND: ' + p.output_template + '; available: ' + templates.join(', ')); }
                module.applyTemplate(selectedTemplate);
                queued.outputModule(1).file = new File(selectedPattern);
                queued.render = true;
                app.project.save(new File(p.project_path));
                previewInfo = {ae_version: app.version, render_copy: app.project.file.fsName, template: selectedTemplate,
                    frame_pattern: selectedPattern, start_time: queued.timeSpanStart, duration: queued.timeSpanDuration,
                    fps: renderComp.frameRate, width: renderComp.width, height: renderComp.height, queue_items: queue.numItems,
                    source_color:deliveryColor(), composition_background:renderComp.bgColor,
                    output_templates:templates, output_settings:module.getSettings(GetSettingsFormat.STRING)};
            } finally {
                if (app.project) { app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES); }
                if (restorePath) { if (!app.open(new File(restorePath))) { throw new Error('Could not restore prior saved project'); } }
                else { app.newProject(); }
            }
        }
        if (p.action === 'effect' || p.action === 'mask') {
            inspect();
            if (app.project.dirty !== false) { throw new Error('ACTIVE_PROJECT_PROTECTED'); }
            var treated = findTarget();
            if (p.action === 'effect' && !treated.layer.property('ADBE Effect Parade').canAddProperty(p.request.effect === 'fill' ? 'ADBE Fill' : 'ADBE Gaussian Blur 2')) { throw new Error('EFFECT_UNAVAILABLE'); }
            var treatmentFile = new File(p.version_path);
            if (treatmentFile.exists) { throw new Error('OUTPUT_EXISTS'); }
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            app.project.save(treatmentFile); p.project_path = p.version_path;
            app.beginUndoGroup('Astra ' + p.action);
            try {
                if (p.action === 'effect') {
                    var addedEffect = treated.layer.property('ADBE Effect Parade').addProperty(p.request.effect === 'fill' ? 'ADBE Fill' : 'ADBE Gaussian Blur 2');
                    addedEffect.name = p.item_name;
                    if (p.request.effect === 'fill') { addedEffect.property('ADBE Fill-0002').setValue(p.request.params.color); }
                    else {
                        addedEffect.property('ADBE Gaussian Blur 2-0001').setValue(p.request.params.amount);
                        addedEffect.property('ADBE Gaussian Blur 2-0003').setValue(p.request.params.repeat_edges ? 1 : 0);
                    }
                } else {
                    var addedMask = treated.layer.property('ADBE Mask Parade').addProperty('ADBE Mask Atom');
                    addedMask.name = p.item_name;
                    var maskShape = new Shape(); maskShape.vertices = p.mask_path.vertices;
                    maskShape.inTangents = p.mask_path.in_tangents; maskShape.outTangents = p.mask_path.out_tangents; maskShape.closed = true;
                    addedMask.property('ADBE Mask Shape').setValue(maskShape);
                    if (p.request.mode === 'add') { addedMask.maskMode = MaskMode.ADD; }
                    else { addedMask.maskMode = MaskMode.SUBTRACT; }
                    addedMask.inverted = p.request.inverted;
                    addedMask.property('ADBE Mask Feather').setValue([p.request.feather, p.request.feather]);
                    addedMask.property('ADBE Mask Opacity').setValue(p.request.opacity);
                }
            } finally { app.endUndoGroup(); }
            app.project.save(treatmentFile);
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(treatmentFile)) { throw new Error('Treatment reopen failed'); }
        }
        if (p.action === 'open_copy') {
            if (!new File(p.project_path).exists) { throw new Error('COPY_NOT_FOUND'); }
            assertSafeToReplace();
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            if (app.project && !app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Could not close safe project'); }
            if (!app.open(new File(p.project_path))) { throw new Error('Could not open working copy'); }
        }
        if (p.action === 'save_version') {
            inspect(); // Explicit save request may capture unsaved edits into a NEW file.
            var saveTarget = new File(p.version_path);
            if (saveTarget.exists) { throw new Error('OUTPUT_EXISTS'); }
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            app.project.save(saveTarget); p.project_path = p.version_path;
            if (!saveTarget.exists || !saveTarget.length) { throw new Error('Version save failed'); }
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(saveTarget)) { throw new Error('Version reopen failed'); }
        }
        if (p.action === 'motion' || p.action === 'transform') {
            inspect();
            var selected = findTarget(); preflightEdit(selected);
            var versionFile = new File(p.version_path);
            if (versionFile.exists) { throw new Error('OUTPUT_EXISTS'); }
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            app.project.save(versionFile); // Source AEP is never overwritten.
            p.project_path = p.version_path;
            app.beginUndoGroup('Astra ' + p.action);
            try {
                if (p.action === 'motion') { applyMotion(selected); }
                else {
                    var propertyName;
                    for (propertyName in p.values) {
                        if (p.values.hasOwnProperty(propertyName)) {
                            var value = p.values[propertyName];
                            transform(selected.layer, propertyName).setValue(adapted(transform(selected.layer, propertyName), value instanceof Array ? value : [value], propertyName, false));
                        }
                    }
                }
            } finally { app.endUndoGroup(); }
            app.project.save(versionFile);
            if (!versionFile.exists || !versionFile.length) { throw new Error('Version save failed'); }
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(versionFile)) { throw new Error('Version reopen failed'); }
        }
        if (p.action === 'snapshot') {
            inspect(); // Require the explicitly approved source project to still be active.
            var backup = new File(p.backup_path);
            if (backup.exists) { throw new Error('OUTPUT_EXISTS: refusing to overwrite a snapshot.'); }
            app.project.save(backup);
            if (!backup.exists || backup.length === 0) { throw new Error('Snapshot save produced no data.'); }
            p.project_path = p.backup_path;
        }
        if (p.action === 'create') {
            var target = new File(p.project_path);
            if (target.exists) { throw new Error('OUTPUT_EXISTS: refusing to overwrite a project.'); }
            assertSafeToReplace();
            if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
            if (app.project && !app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) {
                throw new Error('Could not close the safe project.');
            }
            var project = app.newProject();
            if (!project) { throw new Error('Could not create project.'); }
            var comp = project.items.addComp(p.request.name, p.request.width, p.request.height, 1, p.request.duration, p.request.fps);
            comp.comment = 'astra:composition:' + p.composition_id;
            comp.bgColor = [0.025, 0.035, 0.065];
            var title = comp.layers.addText(p.request.title);
            title.name = 'Title'; title.comment = 'astra:layer:' + p.layer_id;
            var source = title.property('ADBE Text Properties').property('ADBE Text Document');
            var document = source.value;
            document.resetCharStyle(); document.resetParagraphStyle(); document.fontCapsOption = FontCapsOption.FONT_NORMAL_CAPS;
            document.font = 'Arial-BoldMT'; document.fontSize = p.request.font_size;
            document.applyFill = true; document.fillColor = [0.94, 0.96, 1];
            document.applyStroke = false; document.justification = ParagraphJustification.CENTER_JUSTIFY;
            source.setValue(document);
            var bounds = title.sourceRectAtTime(0, false);
            var fit = Math.min(1, comp.width * 0.9 / Math.max(1, bounds.width), comp.height * 0.8 / Math.max(1, bounds.height));
            if (fit < 1) {
                document = source.value; document.fontSize = document.fontSize * fit;
                source.setValue(document); bounds = title.sourceRectAtTime(0, false);
            }
            title.property('ADBE Transform Group').property('ADBE Anchor Point').setValue([bounds.left + bounds.width / 2, bounds.top + bounds.height / 2]);
            title.property('ADBE Transform Group').property('ADBE Position').setValue([comp.width / 2, comp.height / 2]);
            title.inPoint = 0; title.outPoint = comp.duration;
            project.save(target);
            if (!target.exists || target.length === 0) { throw new Error('Project save produced no data.'); }
            // Reopen only the project we just created, proving disk round-trip.
            if (!project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Could not close saved project for verification.'); }
            if (!app.open(target)) { throw new Error('Could not reopen saved project.'); }
        }
        /*ASTRA_RESULT_COLLECTION*/
        if (deliveryInfo !== null) { result.data = deliveryInfo; }
        else if (p.action === 'preview_prepare') { result.data = previewInfo; }
        else if (p.action === 'design_fonts') { result.data = listDesignFonts(p.query); }
        else if (p.action === 'dependencies_inspect') { var dependencyState = inspect(); result.data = {inspection:dependencyState, dependencies:deliveryDependencies(dependencyState)}; }
        else { result.data = inspect(); }
        if (revisionSteps !== null) { result.data.revision_steps = revisionSteps; }
        if (importedAsset) { result.data.imported_asset = importedAsset; }
        if (sceneEditInfo) { result.data.scene_edit = sceneEditInfo; }
        if (p.action === 'snapshot') {
            // This internal action requires explicit operator approval to save and close.
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES)) { throw new Error('Could not close snapshot.'); }
            if (!app.newProject()) { throw new Error('Could not create empty project after snapshot.'); }
        }
        result.status = 'succeeded';
    } catch (error) {
        result.error = String(error) + ' (line ' + error.line + ')';
    }
    // Publish from AE's idle task queue after this invocation has returned.
    // Immediate publication allowed a next -r launch while AE still considered
    // the previous script active. Only a fixed callback plus generated UUID is code.
    if (!$.global.__astraReports) { $.global.__astraReports = {}; }
    var acknowledgement = result;
    if (p.result_protocol === 'artifact-v1') {
        try { acknowledgement = publishNativeResult(result); }
        catch (publicationError) {
            // No valid evidence means no promotion, even with a known script
            // return. Keep incomplete files and let the host retain quarantine.
            acknowledgement = {operation_id:p.operation_id, status:'failed', protocol:'artifact-v1', publication_error:String(publicationError).substring(0,1024)};
        }
    }
    $.global.__astraReports[p.operation_id] = {path: p.result_path, json: encode(acknowledgement)};
    $.global.__astraFlushReport = function (id) {
        var reports = $.global.__astraReports, report = reports[id];
        if (!report) { return; }
        var file = new File(report.path); file.encoding = 'UTF-8';
        if (file.open('w')) {
            try { file.write(report.json); } finally { file.close(); }
            delete reports[id];
            if ($.global.__astraBridge && $.global.__astraBridge.active_job === id) { $.global.__astraBridge.active_job = null; }
        }
    };
    app.scheduleTask('$.global.__astraFlushReport(' + quote(p.operation_id) + ')', 500, false);
}());
