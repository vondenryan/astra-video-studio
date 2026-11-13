//! Offline probes for the pinned AEP importer and one archived visual reference.
#![forbid(unsafe_code)]

use effectcraft_aep::import::{AepImportError, ImportOptions, analyze_with, import};
use effectcraft_keyframe::Value;
use effectcraft_project::{Comp, Footage, ItemId, Layer, LayerSource, Project};
use effectcraft_render::{FootageSource, Image, RenderOpts, Renderer};
use effectcraft_time::{FrameRate, Tick};
use image::ImageEncoder;
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::{fs, io::{Read, Write}, path::Path, process::ExitCode, sync::Arc};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const MAX_AEP_BYTES: u64 = 64 * 1024 * 1024;

fn read_bounded(path: &Path) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    fs::File::open(path)?.take(MAX_AEP_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_AEP_BYTES {
        return Err("AEP exceeds the experiment's byte limit".into());
    }
    Ok(bytes)
}

fn write_json(path: &Path, value: &Json) -> Result<()> {
    fs::File::create_new(path)?.write_all(&serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

fn corpus(directory: &Path) -> Result<Json> {
    let input = directory.join("inputs");
    let mut names = Vec::new();
    for entry in fs::read_dir(input)? {
        let entry = entry?;
        let name = entry.file_name().into_string().map_err(|_| "Invalid corpus name")?;
        if !entry.file_type()?.is_file() || !(name.ends_with(".aep") || name.ends_with(".aepx")) {
            return Err("Unexpected corpus input".into());
        }
        names.push((name, entry.path()));
    }
    names.sort();
    if names.is_empty() || names.len() > 64 {
        return Err("Unexpected corpus size".into());
    }
    let options = ImportOptions { has_font: &|_| false, ..ImportOptions::new(&|_| false) };
    let mut rows = Vec::new();
    for (name, path) in names {
        let bytes = read_bounded(&path)?;
        let baseline = Project::default();
        let mut scratch = baseline.clone();
        let row = match analyze_with(&bytes, &options) {
            Ok(report) => {
                let strict = match import(&mut scratch, &bytes, &options) {
                    Ok(result) if report.is_lossless() && result.report == report => "accepted_in_scratch",
                    Err(AepImportError::Refused(strict_report)) if *strict_report == report && scratch == baseline => {
                        "refused_preserved_scratch"
                    }
                    _ => return Err(format!("{name}: strict import contradicted the dry run").into()),
                };
                json!({"name": name, "status": "analyzed", "strict": strict, "loss_count": report.total_losses(), "report": report})
            }
            Err(error) => {
                if import(&mut scratch, &bytes, &options).is_ok() || scratch != baseline {
                    return Err(format!("{name}: read failure did not preserve scratch").into());
                }
                json!({"name": name, "status": "read_error", "error": error.to_string()})
            }
        };
        rows.push(row);
    }
    Ok(json!({"mode": "corpus", "files": rows}))
}

struct Mark {
    item: ItemId,
    pixels: Arc<Image>,
}

impl FootageSource for Mark {
    fn frame(&self, item: ItemId, _: &Footage, _: Tick) -> Option<Arc<Image>> {
        (item == self.item).then(|| self.pixels.clone())
    }
}

fn named_layer<'a>(comp: &'a Comp, name: &str) -> Result<&'a Layer> {
    let mut candidates = comp.layers.iter().filter(|layer| layer.name == name);
    let layer = candidates.next().ok_or("Missing reference layer")?;
    if candidates.next().is_some() {
        return Err("Ambiguous reference layer".into());
    }
    Ok(layer)
}

fn property(layer: &Layer, name: &str) -> Result<Json> {
    let property = layer.props.prop(name).ok_or("Missing reference property")?;
    Ok(json!(property.value))
}

fn reference(directory: &Path) -> Result<Json> {
    let bytes = read_bounded(&directory.join("reference.aep"))?;
    let mut project = Project::default();
    // This import exists only in scratch memory for comparison. Any loss stays in the report.
    let footage_name = |path: &str| path.rsplit(['/', '\\']).next() == Some("original.png");
    let options = ImportOptions {
        has_font: &|_| false, allow_losses: true, ..ImportOptions::new(&footage_name)
    };
    let imported = import(&mut project, &bytes, &options)?;
    project.settings = imported.settings;
    let [comp_id] = imported.comps.as_slice() else { return Err("Expected a single reference composition".into()); };
    let comp = project.comp(*comp_id).ok_or("Missing composition")?;
    if (comp.width, comp.height, comp.frame_rate) != (1920, 1080, FrameRate::FPS_24)
        || comp.layers.len() != 2 {
        return Err("Unexpected reference composition".into());
    }
    let mark = named_layer(comp, "Collected mark")?;
    let LayerSource::Footage { item: mark_item } = mark.source else {
        return Err("Expected a footage layer".into());
    };
    let title = named_layer(comp, "Title")?;
    let title_id = title.id;
    let opacity = title.props.prop("transform/opacity").ok_or("Missing opacity track")?;
    // Sample the exact five times recorded in the AE inspection.
    let samples = [0.0, 7.5, 15.0, 22.5, 719.0 / 24.0].into_iter().map(|time| {
        let value = effectcraft_keyframe::evaluate(&opacity.keys, Tick::from_seconds_f64(time), false)
            .ok_or("Missing opacity sample")?;
        let Value::Scalar(value) = value else { return Err("Expected scalar opacity".into()); };
        Ok(json!({"time": time, "value": value}))
    }).collect::<Result<Vec<_>>>()?;
    let semantics = json!({
        "width": comp.width, "height": comp.height, "fps": comp.frame_rate.as_f64(),
        "duration": comp.duration.seconds(), "opacity_keys": opacity.keys, "opacity_samples": samples,
        "mark_position": property(mark, "transform/position")?,
        "mark_anchor": property(mark, "transform/anchor")?,
        "mark_scale": property(mark, "transform/scale")?,
        "mark_opacity": property(mark, "transform/opacity")?,
    });
    // The plan fixes a disjoint image ROI. Exclude the title because its historical font
    // bytes were not archived, and never resolve the original AEP's media paths.
    let comp = project.comp_mut(*comp_id).ok_or("Missing composition")?;
    let title = comp.layers.iter_mut().find(|layer| layer.id == title_id).ok_or("Missing title")?;
    title.switches.video = false;
    let pixels = image::open(directory.join("mark.png"))?.into_rgba8();
    if pixels.dimensions() != (64, 64) {
        return Err("Unexpected mark dimensions".into());
    }
    let footage = Mark { item: mark_item, pixels: Arc::new(Image::from_rgba8(64, 64, &pixels)) };
    let renderer = Renderer::new(&project, &footage, RenderOpts::default());
    for index in [0, 3, 5] {
        let frame = renderer.comp_frame(*comp_id, FrameRate::FPS_24.tick_of(72 + index));
        image::codecs::png::PngEncoder::new(fs::File::create_new(directory.join(format!("ec-{index}.png")))?)
            .write_image(&frame.to_rgba8(), 1920, 1080, image::ExtendedColorType::Rgba8)?;
    }
    Ok(json!({"mode": "reference", "semantics": semantics, "import_report": imported.report}))
}

fn compare(directory: &Path) -> Result<Json> {
    let config_bytes = fs::read(directory.join("scene.json"))?;
    if config_bytes.len() > 16 * 1024 { return Err("Oversized scene configuration".into()); }
    let config: Json = serde_json::from_slice(&config_bytes)?;
    let mut faces = Vec::new();
    let mut font_records = Vec::new();
    for font in config["fonts"].as_array().ok_or("Missing fonts")? {
        let file = font["file"].as_str().ok_or("Missing font file")?;
        if !["arial.ttf", "arialbd.ttf"].contains(&file) { return Err("Unexpected font file".into()); }
        let bytes = read_bounded(&directory.join(file))?;
        if format!("{:x}", Sha256::digest(&bytes)) != font["sha256"].as_str().ok_or("Missing font hash")? {
            return Err("Font hash changed".into());
        }
        let ids = effectcraft_text::fonts::add_font_data(bytes);
        let [id] = ids.as_slice() else { return Err("Ambiguous font collection".into()); };
        let face = effectcraft_text::fonts::face(*id);
        if face.info.postscript.as_deref() != font["postscript"].as_str() {
            return Err("Font PostScript identity changed".into());
        }
        faces.push(*id);
        font_records.push(font.clone());
    }
    let has_font = |name: &str| {
        let resolved = effectcraft_text::fonts::resolve(name, "Regular");
        !resolved.missing && !resolved.synth_bold && !resolved.synth_italic && faces.contains(&resolved.face)
    };
    let options = ImportOptions { has_font: &has_font, ..ImportOptions::new(&|_| false) };
    let mut project = Project::default();
    let imported = match import(&mut project, &read_bounded(&directory.join("reference.aep"))?, &options) {
        Ok(imported) => imported,
        Err(AepImportError::Refused(report)) => return Ok(json!({
            "mode": "compare", "status": "refused", "import_report": report,
        })),
        Err(error) => return Err(error.into()),
    };
    if !imported.report.missing_footage.is_empty() || !imported.report.missing_fonts.is_empty()
        || imported.report.imported.expressions != 0 {
        return Err("External dependency, missing font or expression in comparison input".into());
    }
    project.settings = imported.settings;
    let [comp_id] = imported.comps.as_slice() else { return Err("Expected one comparison composition".into()); };
    let comp = project.comp(*comp_id).ok_or("Missing comparison comp")?;
    if config["composition"].as_str() != Some(comp_name(&project, *comp_id)?.as_str())
        || config["native_width"].as_u64() != Some(u64::from(comp.width))
        || config["native_height"].as_u64() != Some(u64::from(comp.height))
        || comp.frame_rate != FrameRate::FPS_24 {
        return Err("Unexpected comparison composition".into());
    }
    let sample_times = config["sample_times"].as_array().ok_or("Missing semantic samples")?;
    if sample_times.len() > 8 { return Err("Too many semantic sample times".into()); }
    let mut layers = Vec::new();
    for layer in &comp.layers {
        let mut tracks = serde_json::Map::new();
        for name in ["position", "anchor", "scale", "rotation", "opacity"] {
            let property = layer.props.prop(&format!("transform/{name}")).ok_or("Missing transform")?;
            if property.expr.is_some() { return Err("Expression in comparison track".into()); }
            let samples = sample_times.iter().map(|time| {
                let time = time.as_f64().ok_or("Invalid sample time")?;
                let value = effectcraft_keyframe::evaluate(&property.keys, Tick::from_seconds_f64(time), property.spatial)
                    .unwrap_or_else(|| property.value.clone());
                Ok(json!({"time": time, "value": value}))
            }).collect::<Result<Vec<_>>>()?;
            tracks.insert(name.into(), json!({"value": property.value, "spatial": property.spatial,
                "keys": property.keys, "samples": samples}));
        }
        let mut text_layout = Json::Null;
        let text = match &layer.source {
            LayerSource::Text => {
                let Value::Text(doc) = &layer.props.prop("text/sourceText").ok_or("Missing source text")?.value
                    else { return Err("Invalid source text value".into()); };
                let resolved = effectcraft_text::fonts::resolve(&doc.font, &doc.style);
                if resolved.missing || resolved.synth_bold || resolved.synth_italic || !faces.contains(&resolved.face) {
                    return Err("Text font was substituted".into());
                }
                let face = effectcraft_text::fonts::face(resolved.face);
                if face.info.postscript.as_deref() != Some(doc.font.as_str()) {
                    return Err("Resolved face differs from the requested PostScript font".into());
                }
                if doc.text.chars().any(|c| c != '\n' && c != '\r' && !face.has_char(c)) {
                    return Err("Text requires a fallback glyph".into());
                }
                let layout = effectcraft_text::layout_doc(doc);
                if layout.layout.missing_font || layout.layout.glyphs.iter().any(|glyph| {
                    glyph.id == 0 || glyph.face != resolved.face || glyph.synth_bold || glyph.synth_italic
                }) {
                    return Err("Comparison glyph layout substituted a face or synthesized a style".into());
                }
                let font_index = faces.iter().position(|id| *id == resolved.face).ok_or("Unpinned layout font")?;
                text_layout = json!({"bounds": layout.bounds, "glyphs": layout.layout.glyphs.len(),
                    "postscript": face.info.postscript, "font_sha256": font_records[font_index]["sha256"],
                    "family": face.info.family, "style": face.info.style, "glyph_faces_verified": true});
                Some(json!(doc))
            }
            _ => None,
        };
        layers.push(json!({"name": layer.name, "tracks": tracks, "text": text, "text_layout": text_layout}));
    }
    let frames = config["frames"].as_array().ok_or("Missing comparison frames")?;
    if frames.is_empty() || frames.len() > 8 { return Err("Unexpected comparison frame count".into()); }
    let bg = config["background"].as_array().ok_or("Missing native background")?;
    if bg.len() != 3 { return Err("Invalid native background".into()); }
    let background = [bg[0].as_f64().ok_or("Invalid background")? as f32,
        bg[1].as_f64().ok_or("Invalid background")? as f32, bg[2].as_f64().ok_or("Invalid background")? as f32];
    let renderer = Renderer::new(&project, &effectcraft_render::NoFootage, RenderOpts::default());
    for frame in frames {
        let frame = frame.as_i64().ok_or("Invalid comparison frame")?;
        if frame < 0 || FrameRate::FPS_24.tick_of(frame) >= comp.duration {
            return Err("Frame outside comparison composition".into());
        }
        let image = renderer.comp_frame(*comp_id, FrameRate::FPS_24.tick_of(frame));
        let pixels = image.to_rgba8_over(background);
        image::codecs::png::PngEncoder::new(fs::File::create_new(directory.join(format!("ec-{frame}.png")))?)
            .write_image(&pixels, comp.width, comp.height, image::ExtendedColorType::Rgba8)?;
        image::codecs::png::PngEncoder::new(fs::File::create_new(directory.join(format!("ec-rgba-{frame}.png")))?)
            .write_image(&image.to_rgba8(), comp.width, comp.height, image::ExtendedColorType::Rgba8)?;
    }
    Ok(json!({"mode": "compare", "status": "rendered", "import_report": imported.report, "layers": layers, "fonts": font_records,
        "font_system_scanned": effectcraft_text::fonts::system_scanned()}))
}

fn comp_name(project: &Project, id: ItemId) -> Result<String> {
    Ok(project.item(id).ok_or("Missing composition item")?.name.clone())
}

fn run() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let [_, mode, directory] = args.as_slice() else { return Err("Expected mode and private directory".into()); };
    let directory = Path::new(directory).canonicalize()?;
    let report = match mode.as_str() {
        "corpus" => corpus(&directory)?,
        "reference" => reference(&directory)?,
        "compare" => compare(&directory)?,
        _ => return Err("Unsupported mode".into()),
    };
    write_json(&directory.join("worker-report.json"), &report)?;
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            let _ = writeln!(std::io::stderr().lock(), "{error}");
            ExitCode::FAILURE
        }
    }
}
