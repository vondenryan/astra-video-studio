// Bounded native creation only. IDs and all values are generated/serialized data.
function runLayerBatch() {
    var before=inspect(), comp=sceneComp(p.composition_id), i, item, fonts=[], file=new File(p.version_path), original=p.project_path;
    if (app.project.dirty !== false || encode(before.compositions)!==encode(p.expected_state.compositions) || encode(before.footage)!==encode(p.expected_state.footage)) { throw new Error('STATE_CONFLICT'); }
    if (file.exists) { throw new Error('OUTPUT_EXISTS'); }
    for (i=0;i<p.items.length;i++) {
        item=p.items[i];fonts.push(item.text_style ? resolveDesignFont(item.text_style.font) : null);
        if (item.layer.in_point>=comp.duration || item.layer.out_point!==null && item.layer.out_point>comp.duration) { throw new Error('LAYER_INTERVAL'); }
    }
    if (new File(p.cancel_path).exists) { throw new Error('CANCELLED'); }
    app.project.save(file);p.project_path=p.version_path;
    var failure=null;
    try {
        for (i=0;i<p.items.length;i++) {
            item=p.items[i];var layer=addLayer(comp,item.layer,item.layer_id,null);
            if (item.text_style) {
                var prop=layer.property('ADBE Text Properties').property('ADBE Text Document'),doc=prop.value;
                doc.fontObject=fonts[i];doc.fontSize=item.layer.font_size;doc.tracking=item.layer.tracking;
                doc.justification=alignValue(item.text_style.alignment);
                if (item.text_style.leading!==null) { doc.autoLeading=false;doc.leading=item.text_style.leading; }
                prop.setValue(doc);
                if (prop.value.boxText && prop.value.boxOverflow) { throw new Error('BATCH_TEXT_OVERFLOW'); }
                var rect=layer.sourceRectAtTime(0,false);
                transform(layer,'anchor').setValue([rect.left+rect.width/2,rect.top+rect.height/2]);
            }
        }
    } catch (error) { failure=error; }
    app.project.save(file);
    if (failure) {
        // Synchronous design failure in this disposable copy only. A host
        // timeout is quarantined, never handled as a source-restoration retry.
        if (!new File(p.cancel_path).exists) {
            if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(new File(original))) { throw new Error('Batch source restore failed'); }
            p.project_path=original;
        }
        throw failure;
    }
    if (!app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES) || !app.open(file)) { throw new Error('Batch reopen failed'); }
}
