//! Native EffectCraft compositing fixtures, isolated from the Astra production backend.
#![forbid(unsafe_code)]

use effectcraft_color::Label;
use effectcraft_keyframe::{Keyframe, ShapePath, Value};
use effectcraft_project::{
    Comp, ItemId, ItemKind, Layer, LayerId, LayerSource, MaskMode, MatteKind, Project, Solid,
    TrackMatte, build::{self, Ids},
};
use effectcraft_render::{NoFootage, RenderOpts, Renderer};
use effectcraft_time::{FrameRate, Tick};
use image::ImageEncoder;
use serde_json::{Value as Json, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::Write,
    path::Path,
    process::ExitCode,
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const WIDTH: u32 = 160;
const HEIGHT: u32 = 120;
const REVISION: &str = "a41ff5015c6687db15a6f074a47b870b8f09fece";

fn add_comp(project: &mut Project, name: &str) -> (ItemId, Comp) {
    let comp = Comp::new(WIDTH, HEIGHT, FrameRate::FPS_30, FrameRate::FPS_30.tick_of(31));
    let id = project.add_item(name, Label::Sandstone, None, ItemKind::Comp(comp.clone().into()));
    (id, comp)
}

fn solid(project: &mut Project, comp: &Comp, name: &str, color: [f32; 3], size: (u32, u32)) -> Layer {
    let item = project.add_item(name, Label::Aqua, None, ItemKind::Solid(Solid {
        color, width: size.0, height: size.1, pixel_aspect: 1.0,
    }));
    build::layer(project, comp, name, LayerSource::Solid { item }, size, None)
}

fn position(layer: &mut Layer, x: f64, y: f64) -> Result<()> {
    layer.props.prop_mut("transform/position").ok_or("Missing position")?.value =
        Value::Vec3([x, y, 0.0]);
    Ok(())
}

fn add_layers(project: &mut Project, id: ItemId, layers: impl IntoIterator<Item = Layer>) -> Result<()> {
    let comp = project.comp_mut(id).ok_or("Missing composition")?;
    for layer in layers {
        comp.layers.push(layer);
    }
    Ok(())
}

fn effect(project: &mut Project, layer: &mut Layer, id: &str, parameter: &str, value: Value) -> Result<()> {
    let spec = effectcraft_effects::find(id).ok_or("Missing effect specification")?;
    let mut group = effectcraft_effects::instantiate(
        spec, &mut Ids(&mut project.next_id), spec.name, [64.0, 48.0],
    );
    group.prop_mut(parameter).ok_or("Missing effect parameter")?.value = value;
    layer.props.sub_mut("effects").ok_or("Missing effects group")?.children.push(group.into());
    Ok(())
}

fn vector(project: &mut Project, comp: &Comp, name: &str, path: ShapePath, color: [f64; 4]) -> Result<Layer> {
    let mut layer = build::layer(project, comp, name, LayerSource::Shape, (0, 0), None);
    position(&mut layer, 0.0, 0.0)?;
    let ids = &mut Ids(&mut project.next_id);
    let path = build::shape_path(ids, path);
    let fill = build::shape_fill(ids, color);
    let group = build::shape_group(ids, name, vec![path, fill]);
    layer.props.sub_mut("contents").ok_or("Missing shape contents")?.children.push(group.into());
    Ok(layer)
}

fn fixture() -> Result<(Project, BTreeMap<&'static str, ItemId>)> {
    let mut project = Project::default();
    let mut cases = BTreeMap::new();

    let (id, comp) = add_comp(&mut project, "Fill");
    let mut layer = solid(&mut project, &comp, "Fill source", [1.0, 0.0, 0.0], (64, 48));
    effect(&mut project, &mut layer, "ec.generate.fill", "color", Value::Color([0.0, 1.0, 0.0, 1.0]))?;
    add_layers(&mut project, id, [layer])?;
    cases.insert("fill", id);

    let (id, comp) = add_comp(&mut project, "Gaussian Blur");
    let mut layer = solid(&mut project, &comp, "Blur source", [1.0; 3], (64, 48));
    effect(&mut project, &mut layer, "ec.blur.gaussian", "blurriness", Value::Scalar(10.0))?;
    add_layers(&mut project, id, [layer])?;
    cases.insert("blur", id);

    let (id, comp) = add_comp(&mut project, "Vector paint order");
    let front = vector(&mut project, &comp, "Front", ShapePath::rect([96.0, 60.0], 64.0, 48.0), [1.0, 0.0, 0.0, 1.0])?;
    let back = vector(&mut project, &comp, "Back", ShapePath::rect([64.0, 60.0], 64.0, 48.0), [0.0, 1.0, 0.0, 1.0])?;
    add_layers(&mut project, id, [front, back])?;
    cases.insert("vectors", id);

    let (id, comp) = add_comp(&mut project, "Trim Paths");
    let mut layer = build::layer(&mut project, &comp, "Open line", LayerSource::Shape, (0, 0), None);
    position(&mut layer, 0.0, 0.0)?;
    let ids = &mut Ids(&mut project.next_id);
    let line = ShapePath::polygon(&[[24.0, 60.0], [136.0, 60.0]], false);
    let path = build::shape_path(ids, line);
    let trim = build::shape_trim(ids, 0.0, 50.0, 0.0);
    let stroke = build::shape_stroke(ids, [1.0; 4], 8.0);
    let group = build::shape_group(ids, "Line", vec![path, trim, stroke]);
    layer.props.sub_mut("contents").ok_or("Missing shape contents")?.children.push(group.into());
    add_layers(&mut project, id, [layer])?;
    cases.insert("trim", id);

    let (id, comp) = add_comp(&mut project, "Path morph");
    let initial = ShapePath::rect([48.0, 60.0], 24.0, 24.0);
    let mut layer = build::layer(&mut project, &comp, "Morph rectangle", LayerSource::Shape, (0, 0), None);
    position(&mut layer, 0.0, 0.0)?;
    let ids = &mut Ids(&mut project.next_id);
    let mut path = build::shape_path(ids, initial.clone());
    path.prop_mut("path").ok_or("Missing vector path")?.keys = vec![
        Keyframe::new(Tick::ZERO, Value::Path(initial)),
        Keyframe::new(FrameRate::FPS_30.tick_of(30), Value::Path(ShapePath::rect([112.0, 60.0], 24.0, 24.0))),
    ];
    let fill = build::shape_fill(ids, [0.0, 0.0, 1.0, 1.0]);
    let group = build::shape_group(ids, "Morph", vec![path, fill]);
    layer.props.sub_mut("contents").ok_or("Missing shape contents")?.children.push(group.into());
    add_layers(&mut project, id, [layer])?;
    cases.insert("morph", id);

    let (id, comp) = add_comp(&mut project, "Mask hole");
    let mut layer = solid(&mut project, &comp, "Masked solid", [1.0, 1.0, 0.0], (WIDTH, HEIGHT));
    let ids = &mut Ids(&mut project.next_id);
    let add = build::mask(ids, "Outer", ShapePath::rect([80.0, 60.0], 100.0, 80.0), MaskMode::Add, [255; 3]);
    let hole = build::mask(ids, "Hole", ShapePath::rect([80.0, 60.0], 24.0, 24.0), MaskMode::Subtract, [255; 3]);
    let masks = layer.props.sub_mut("masks").ok_or("Missing mask group")?;
    masks.children.extend([add.into(), hole.into()]);
    add_layers(&mut project, id, [layer])?;
    cases.insert("mask", id);

    for (name, mode, color) in [
        ("alpha-matte", MatteKind::Alpha, [0.0; 3]),
        ("luma-matte", MatteKind::Luma, [0.0; 3]),
        ("luma-control", MatteKind::Luma, [1.0; 3]),
    ] {
        let (id, comp) = add_comp(&mut project, name);
        let mut matte = solid(&mut project, &comp, "Matte", color, (64, 48));
        matte.switches.video = false;
        let mut target = solid(&mut project, &comp, "Matte target", [0.0, 1.0, 1.0], (WIDTH, HEIGHT));
        target.track_matte = Some(TrackMatte { layer: matte.id, kind: mode });
        add_layers(&mut project, id, [matte, target])?;
        cases.insert(name, id);
    }

    let (inner_id, inner) = add_comp(&mut project, "Nested source");
    let mut parent = build::layer(&mut project, &inner, "Offset null", LayerSource::Null, (100, 100), None);
    parent.props.prop_mut("transform/anchor").ok_or("Missing anchor")?.value = Value::Vec3([0.0; 3]);
    position(&mut parent, 32.0, 0.0)?;
    let mut child = solid(&mut project, &inner, "Parented solid", [1.0, 0.0, 1.0], (20, 20));
    child.parent = Some(parent.id);
    add_layers(&mut project, inner_id, [child, parent])?;
    let (id, comp) = add_comp(&mut project, "Nested and parented");
    let nested = build::layer(&mut project, &comp, "Nested source", LayerSource::Comp { item: inner_id }, (WIDTH, HEIGHT), None);
    add_layers(&mut project, id, [nested])?;
    cases.insert("precomp-parent", id);
    Ok((project, cases))
}

fn acyclic<T: Copy + Ord>(mut graph: BTreeMap<T, BTreeSet<T>>) -> bool {
    while !graph.is_empty() {
        let ready: BTreeSet<_> = graph.iter().filter_map(|(&node, edges)| edges.is_empty().then_some(node)).collect();
        if ready.is_empty() {
            return false;
        }
        graph.retain(|node, edges| {
            edges.retain(|edge| !ready.contains(edge));
            !ready.contains(node)
        });
    }
    true
}

fn validate_graph(project: &Project) -> Result<()> {
    let mut comps = BTreeMap::<ItemId, BTreeSet<ItemId>>::new();
    for (&id, item) in &project.items {
        let ItemKind::Comp(comp) = &item.kind else { continue };
        let edges = comps.entry(id).or_default();
        let mut layers = BTreeMap::<LayerId, BTreeSet<LayerId>>::new();
        let ids: BTreeSet<_> = comp.layers.iter().map(|layer| layer.id).collect();
        for layer in comp.layers.iter() {
            let mut dependencies = BTreeSet::new();
            if let Some(parent) = layer.parent {
                if !ids.contains(&parent) { return Err("missing-parent".into()); }
                dependencies.insert(parent);
            }
            if let Some(matte) = &layer.track_matte {
                if !ids.contains(&matte.layer) { return Err("missing-matte".into()); }
                dependencies.insert(matte.layer);
            }
            if let LayerSource::Comp { item } = layer.source {
                if project.comp(item).is_none() { return Err("missing-precomp".into()); }
                edges.insert(item);
            }
            layers.insert(layer.id, dependencies);
        }
        if !acyclic(layers) { return Err("layer-cycle".into()); }
    }
    if !acyclic(comps) { return Err("precomp-cycle".into()); }
    Ok(())
}

fn negative_cases() -> Result<Json> {
    let mut results = Vec::new();
    for case in ["missing-parent", "missing-matte", "missing-precomp", "layer-cycle", "matte-cycle", "mixed-layer-cycle", "precomp-cycle"] {
        let mut project = Project::default();
        let (id, comp) = add_comp(&mut project, "Negative fixture");
        let mut a = build::layer(&mut project, &comp, "A", LayerSource::Null, (100, 100), None);
        let mut b = build::layer(&mut project, &comp, "B", LayerSource::Null, (100, 100), None);
        let expected = match case {
            "missing-parent" => { a.parent = Some(LayerId(u64::MAX)); case }
            "missing-matte" => { a.track_matte = Some(TrackMatte { layer: LayerId(u64::MAX), kind: MatteKind::Alpha }); case }
            "missing-precomp" => { a.source = LayerSource::Comp { item: ItemId(u64::MAX) }; case }
            "precomp-cycle" => {
                let (inner, inner_comp) = add_comp(&mut project, "Second composition");
                a.source = LayerSource::Comp { item: inner };
                let back = build::layer(&mut project, &inner_comp, "Back edge", LayerSource::Comp { item: id }, (WIDTH, HEIGHT), None);
                add_layers(&mut project, inner, [back])?;
                case
            }
            "layer-cycle" => { a.parent = Some(b.id); b.parent = Some(a.id); "layer-cycle" }
            "matte-cycle" => {
                a.track_matte = Some(TrackMatte { layer: b.id, kind: MatteKind::Alpha });
                b.track_matte = Some(TrackMatte { layer: a.id, kind: MatteKind::Alpha });
                "layer-cycle"
            }
            _ => {
                a.parent = Some(b.id);
                b.track_matte = Some(TrackMatte { layer: a.id, kind: MatteKind::Alpha });
                "layer-cycle"
            }
        };
        add_layers(&mut project, id, [a, b])?;
        let error = validate_graph(&project).err().ok_or("Invalid dependency was accepted")?;
        if error.to_string() != expected { return Err(error); }
        results.push(json!({"case": case, "refusal": expected}));
    }
    Ok(json!(results))
}

fn exclusive(path: &Path) -> Result<File> {
    Ok(OpenOptions::new().write(true).create_new(true).open(path)?)
}

fn run(args: &[String]) -> Result<Json> {
    let [_, root_flag, root, job_flag, job] = args else { return Err("Invalid arguments".into()); };
    if root_flag != "--root" || job_flag != "--job" || job.len() != 32 ||
        !job.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)) {
        return Err("Invalid job arguments".into());
    }
    let directory = Path::new(root).canonicalize()?.join(job);
    let (project, cases) = fixture()?;
    validate_graph(&project)?;
    let refused = negative_cases()?;
    fs::create_dir(&directory)?;
    let saved = directory.join("project.ecproj");
    exclusive(&saved)?.write_all(project.to_file_json()?.as_bytes())?;
    let (reopened, repairs) = Project::from_json_repaired(&fs::read_to_string(saved)?)?;
    if reopened != project || !repairs.is_empty() { return Err("Roundtrip changed project".into()); }
    validate_graph(&reopened)?;
    let renderer = Renderer::new(&reopened, &NoFootage, RenderOpts::default());
    for (name, id) in cases {
        let frames: &[i64] = if name == "morph" { &[0, 15, 30] } else { &[0] };
        for frame in frames {
            let image = renderer.comp_frame(id, FrameRate::FPS_30.tick_of(*frame));
            image::codecs::png::PngEncoder::new(exclusive(&directory.join(format!("{name}-{frame}.png")))?)
                .write_image(&image.to_rgba8(), WIDTH, HEIGHT, image::ExtendedColorType::Rgba8)?;
        }
    }
    let result = json!({
        "protocol": "astra-ec0-compositing-v1", "job_id": job, "status": "succeeded",
        "revision": REVISION, "roundtrip_equal": true, "dependency_refusals": refused
    });
    exclusive(&directory.join("result.json"))?.write_all(&serde_json::to_vec(&result)?)?;
    Ok(result)
}

fn main() -> ExitCode {
    let args: Vec<_> = std::env::args().collect();
    let (receipt, code) = match run(&args) {
        Ok(receipt) => (receipt, ExitCode::SUCCESS),
        Err(error) => (json!({"status": "failed", "error": error.to_string()}), ExitCode::FAILURE),
    };
    if writeln!(std::io::stdout().lock(), "{receipt}").is_err() { return ExitCode::FAILURE; }
    code
}
