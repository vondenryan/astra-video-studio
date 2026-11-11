use super::{HEIGHT, REVISION, Result, WIDTH, exclusive, position};
use effectcraft_color::Label;
use effectcraft_keyframe::{ShapePath, Value};
use effectcraft_project::{Comp, ItemId, ItemKind, Layer, LayerId, LayerSource, Project, build::{self, Ids}};
use effectcraft_render::{NoFootage, RenderOpts, Renderer};
use effectcraft_time::{FrameRate, Tick};
use image::ImageEncoder;
use serde_json::{Value as Json, json};
use std::{fs, io::{Read, Write}, path::Path};

struct Paint {
    rgba: [f64; 4],
    opacity: f64,
    width: Option<f64>,
}

impl Paint {
    fn parse(value: &Json, stroke: bool) -> Result<Option<Self>> {
        if value.is_null() {
            return Ok(None);
        }
        let [r, g, b]: [f64; 3] = serde_json::from_value(value["color"].clone())?;
        let opacity = value["opacity"].as_f64().ok_or("Missing paint opacity")?;
        if [r, g, b].iter().any(|c| !(0.0..=1.0).contains(c))
            || !(0.0..=100.0).contains(&opacity) {
            return Err("Paint outside allowed range".into());
        }
        let width = if stroke {
            let width = value["width"].as_f64().ok_or("Missing stroke width")?;
            if !(0.0 < width && width <= 200.0) || value["cap"] != 1 || value["join"] != 1 {
                return Err("Unsupported stroke width, cap or join".into());
            }
            Some(width)
        } else {
            None
        };
        Ok(Some(Self { rgba: [r, g, b, 1.0], opacity, width }))
    }
}

fn readback(layer: &Layer, path_uid: u64, paints: [Option<u64>; 2]) -> Result<Json> {
    let lookup = |uid| layer.props.prop(&format!("@{uid}")).ok_or("Missing imported property");
    let Value::Path(path) = &lookup(path_uid)?.value else {
        return Err("Imported property must remain a native path".into());
    };
    let read_paint = |uid: Option<u64>, stroke: bool| -> Result<Json> {
        let Some(uid) = uid else { return Ok(Json::Null); };
        let group = layer.props.parent_of(uid).ok_or("Missing paint group")?;
        let read = |name| -> Result<Json> {
            Ok(serde_json::to_value(&group.prop(name).ok_or("Missing paint parameter")?.value)?["v"].clone())
        };
        let mut paint = json!({"rgba": read("color")?, "opacity": read("opacity")?});
        if stroke {
            paint["width"] = read("width")?;
            paint["cap"] = read("cap")?;
            paint["join"] = read("join")?;
        }
        Ok(paint)
    };
    Ok(json!({"path": path, "fill": read_paint(paints[0], false)?, "stroke": read_paint(paints[1], true)?}))
}

fn replace_fill(project: &mut Project, comp: ItemId, layer: LayerId, uid: u64, color: Value) -> Result<Value> {
    let comp = project.comp_mut(comp).ok_or("Missing comp")?;
    let layer = comp.layers.iter_mut().find(|item| item.id == layer).ok_or("Missing SVG layer")?;
    let property = layer.props.prop_mut(&format!("@{uid}")).ok_or("Missing top fill")?;
    Ok(std::mem::replace(&mut property.value, color))
}

pub fn run(directory: &Path, job: &str) -> Result<Json> {
    let mut input = Vec::new();
    std::io::stdin().lock().take(1_048_577).read_to_end(&mut input)?;
    if input.len() > 1_048_576 {
        return Err("Normalized SVG plan exceeds byte limit".into());
    }
    let plan: Json = serde_json::from_slice(&input)?;
    let groups = plan.as_array().ok_or("SVG group list required")?;
    if !(1..=32).contains(&groups.len()) {
        return Err("Unsupported group count".into());
    }

    let mut project = Project::default();
    let comp = Comp::new(WIDTH, HEIGHT, FrameRate::FPS_30, FrameRate::FPS_30.tick_of(1));
    let comp_id = project.add_item("Editable SVG", Label::Sandstone, None, ItemKind::Comp(comp.clone().into()));
    let mut layer = build::layer(&mut project, &comp, "SVG", LayerSource::Shape, (0, 0), None);
    position(&mut layer, f64::from(WIDTH) / 2.0, f64::from(HEIGHT) / 2.0)?;
    let mut properties = Vec::new();
    let mut vertex_count = 0;
    let ids = &mut Ids(&mut project.next_id);
    // EffectCraft's layer stack is front first. SVG document order is back first.
    for (index, group) in groups.iter().enumerate().rev() {
        let path: ShapePath = serde_json::from_value(group["path"].clone())?;
        let count = path.vertices.len();
        vertex_count += count;
        if count < if path.closed { 3 } else { 2 }
            || count > 256 || vertex_count > 4096
            || path.in_tangents.len() != count || path.out_tangents.len() != count
            || path.vertices.iter().chain(&path.in_tangents).chain(&path.out_tangents)
                .flatten().any(|value| !value.is_finite() || value.abs() > 20_000.0) {
            return Err("Invalid native SVG geometry".into());
        }
        let path = build::shape_path(ids, path);
        let path_uid = path.prop("path").ok_or("Missing path")?.uid;
        let mut children = vec![path];
        let mut paints = [None; 2];
        for (slot, name) in ["fill", "stroke"].into_iter().enumerate() {
            if let Some(paint) = Paint::parse(&group[name], slot == 1)? {
                let mut native = match paint.width {
                    Some(width) => build::shape_stroke(ids, paint.rgba, width),
                    None => build::shape_fill(ids, paint.rgba),
                };
                native.prop_mut("opacity").ok_or("Missing opacity")?.value = Value::Scalar(paint.opacity);
                paints[slot] = Some(native.prop("color").ok_or("Missing color")?.uid);
                children.push(native);
            }
        }
        properties.push((path_uid, paints));
        let native = build::shape_group(ids, &format!("SVG {}", index + 1), children);
        layer.props.sub_mut("contents").ok_or("Missing shape contents")?.children.push(native.into());
    }
    let layer_id = layer.id;
    project.comp_mut(comp_id).ok_or("Missing comp")?.layers.push(layer);

    fs::create_dir(directory)?;
    let source = directory.join("project.ecproj");
    exclusive(&source)?.write_all(project.to_file_json()?.as_bytes())?;
    let (mut reopened, repairs) = Project::from_json_repaired(&fs::read_to_string(&source)?)?;
    if project != reopened || !repairs.is_empty() {
        return Err("SVG roundtrip changed project".into());
    }
    let render = |project: &Project, name| -> Result<()> {
        let image = Renderer::new(project, &NoFootage, RenderOpts::default()).comp_frame(comp_id, Tick::ZERO);
        image::codecs::png::PngEncoder::new(exclusive(&directory.join(name))?)
            .write_image(&image.to_rgba8(), WIDTH, HEIGHT, image::ExtendedColorType::Rgba8)?;
        Ok(())
    };
    render(&reopened, "svg-before.png")?;
    let layer = reopened.comp(comp_id).ok_or("Missing comp")?.layers.iter()
        .find(|layer| layer.id == layer_id).ok_or("Missing SVG layer")?;
    let inspection = properties.iter().rev().map(|(path, paint)| readback(layer, *path, *paint))
        .collect::<Result<Vec<_>>>()?;
    let fill_uid = properties.first().and_then(|entry| entry.1[0]).ok_or("Missing top fill")?;
    let original_fill = replace_fill(&mut reopened, comp_id, layer_id, fill_uid, Value::Color([0.0, 0.0, 1.0, 1.0]))?;
    let revised = directory.join("edited.ecproj");
    exclusive(&revised)?.write_all(reopened.to_file_json()?.as_bytes())?;
    let (edited, repairs) = Project::from_json_repaired(&fs::read_to_string(revised)?)?;
    if edited != reopened || !repairs.is_empty()
        || Project::from_json_repaired(&fs::read_to_string(source)?)?.0 != project {
        return Err("SVG edit persistence or original project mismatch".into());
    }
    let mut restored = edited.clone();
    replace_fill(&mut restored, comp_id, layer_id, fill_uid, original_fill)?;
    if restored != project {
        return Err("An unrelated property changed in the SVG edit".into());
    }
    render(&edited, "svg-after.png")?;
    exclusive(&directory.join("paths.json"))?.write_all(&serde_json::to_vec(&inspection)?)?;
    let result = json!({
        "protocol": "astra-ec0-svg-v1", "job_id": job, "status": "succeeded",
        "revision": REVISION, "roundtrip_equal": true, "native_paths": groups.len(),
        "edited_fill_uid": fill_uid,
    });
    exclusive(&directory.join("result.json"))?.write_all(&serde_json::to_vec(&result)?)?;
    Ok(result)
}
