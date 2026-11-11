use super::{HEIGHT, REVISION, Result, WIDTH, exclusive, pinned_font::strict_font, position};
use effectcraft_color::Label;
use effectcraft_keyframe::{Keyframe, TextDoc, Value};
use effectcraft_project::{Comp, ItemKind, LayerSource, Project, build::{self, Ids}};
use effectcraft_render::{NoFootage, RenderOpts, Renderer};
use effectcraft_text::{fonts, layout_doc};
use effectcraft_time::FrameRate;
use image::ImageEncoder;
use serde_json::{Value as Json, json};
use std::{fs, io::Write, path::Path};

const FONT: &str = "JetBrainsMono-Regular";
const SHA: &str = "e6fd0d7e91550b3ed2b735d4312474362c4716edc4fc0577a0f61ed782d5aed1";

pub fn run(directory: &Path, job: &str) -> Result<Json> {
    let doc = TextDoc { text: "HH".into(), font: FONT.into(), size: 48.0, ..TextDoc::default() };
    let face = strict_font(FONT, &doc.text, SHA)?;
    let layout = layout_doc(&doc);
    if layout.layout.missing_font || layout.layout.glyphs.len() != 2
        || layout.layout.glyphs.iter().any(|glyph| glyph.face != face || glyph.id == 0 || glyph.synth_bold || glyph.synth_italic) {
        return Err("Layout substituted the pinned font".into());
    }
    let mut project = Project::default();
    let rate = FrameRate::FPS_30;
    let comp = Comp::new(WIDTH, HEIGHT, rate, rate.tick_of(31));
    let comp_id = project.add_item("Text range selector", Label::Sandstone, None, ItemKind::Comp(comp.clone().into()));
    let mut layer = build::layer(&mut project, &comp, "HH", LayerSource::Text, (0, 0), None);
    position(&mut layer, 32.0, 80.0)?;
    layer.props.prop_mut("text/sourceText").ok_or("Missing source text")?.value = Value::Text(Box::new(doc));
    let ids = &mut Ids(&mut project.next_id);
    let mut opacity = build::text_anim_prop(ids, "opacity").ok_or("Missing opacity animator")?;
    opacity.value = Value::Scalar(0.0);
    let mut animator = build::text_animator(ids, "Reveal", vec![opacity]);
    let selector = animator.group_mut("selectors/rangeSelector").ok_or("Missing range selector")?;
    selector.prop_mut("advanced/smoothness").ok_or("Missing smoothness")?.value = Value::Scalar(0.0);
    selector.prop_mut("end").ok_or("Missing range end")?.keys = vec![
        Keyframe::new(rate.tick_of(0), Value::Scalar(100.0)),
        Keyframe::new(rate.tick_of(30), Value::Scalar(0.0)),
    ];
    layer.props.group_mut("text/animators").ok_or("Missing animator group")?.children.push(animator.into());
    project.comp_mut(comp_id).ok_or("Missing comp")?.layers.push(layer);

    fs::create_dir(directory)?;
    let source = directory.join("project.ecproj");
    exclusive(&source)?.write_all(project.to_file_json()?.as_bytes())?;
    let (reopened, repairs) = Project::from_json_repaired(&fs::read_to_string(source)?)?;
    if reopened != project || !repairs.is_empty() {
        return Err("Animator roundtrip changed project".into());
    }
    let renderer = Renderer::new(&reopened, &NoFootage, RenderOpts::default());
    for frame in [0, 15, 30] {
        let image = renderer.comp_frame(comp_id, rate.tick_of(frame));
        image::codecs::png::PngEncoder::new(exclusive(&directory.join(format!("selector-{frame}.png")))?)
            .write_image(&image.to_rgba8(), WIDTH, HEIGHT, image::ExtendedColorType::Rgba8)?;
    }
    if fonts::system_scanned() {
        return Err("Unexpected system font discovery".into());
    }
    let result = json!({
        "protocol": "astra-ec0-text-selector-v1", "job_id": job, "status": "succeeded",
        "revision": REVISION, "roundtrip_equal": true, "font_postscript": FONT,
        "font_sha256": SHA, "system_fonts_scanned": false,
    });
    exclusive(&directory.join("result.json"))?.write_all(&serde_json::to_vec(&result)?)?;
    Ok(result)
}
