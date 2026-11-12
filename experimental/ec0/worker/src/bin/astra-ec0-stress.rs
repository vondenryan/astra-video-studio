//! Fixed 1080p CPU resource probes with no connection to the AE session.
#![forbid(unsafe_code)]

use effectcraft_color::Label;
use effectcraft_keyframe::{Interp, Keyframe, Value};
use effectcraft_project::{build, Comp, ItemId, ItemKind, Layer, LayerSource, Project, Solid};
use effectcraft_render::{NoFootage, RenderOpts, Renderer};
use effectcraft_time::FrameRate;
use image::ImageEncoder;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{fs, io::Write, path::Path, process::ExitCode, time::Instant};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const SAMPLES: [i64; 5] = [0, 225, 450, 675, 899];

fn solid(project: &mut Project, comp: &Comp, name: &str, color: [f32; 3], size: (u32, u32)) -> Layer {
    let item = project.add_item(name, Label::Aqua, None, ItemKind::Solid(Solid {
        color, width: size.0, height: size.1, pixel_aspect: 1.0,
    }));
    build::layer(project, comp, name, LayerSource::Solid { item }, size, None)
}

fn set_position(layer: &mut Layer, value: [f64; 3]) -> Result<()> {
    layer.props.prop_mut("transform/position").ok_or("Missing position")?.value = Value::Vec3(value);
    Ok(())
}

fn fixture(count: usize) -> Result<(Project, ItemId)> {
    let mut project = Project::default();
    let duration = FrameRate::FPS_30.tick_of(900);
    let comp = Comp::new(1920, 1080, FrameRate::FPS_30, duration);
    let comp_id = project.add_item("1080p root", Label::Sandstone, None, ItemKind::Comp(comp.clone().into()));
    let inner = Comp::new(160, 90, FrameRate::FPS_30, duration);
    let inner_id = project.add_item("Nested three-layer comp", Label::Sandstone, None, ItemKind::Comp(inner.clone().into()));
    let mut inner_layers = Vec::new();
    for index in 0..3 {
        let mut layer = solid(&mut project, &inner, "Nested green", [0.0, 1.0, 0.0], (32, 16));
        set_position(&mut layer, [30.0 + index as f64 * 50.0, 20.0 + index as f64 * 25.0, 0.0])?;
        inner_layers.push(layer);
    }
    project.comp_mut(inner_id).ok_or("Missing inner comp")?.layers = inner_layers.into();
    let mut layers = Vec::new();
    for index in 0..count - 2 {
        let mut layer = solid(&mut project, &comp, "Moving red", [1.0, 0.0, 0.0], (64, 32));
        let start = [90.0 + (index % 10) as f64 * 180.0, 100.0 + (index / 10) as f64 * 110.0, 0.0];
        let finish = [start[0] + 45.0, start[1] + 20.0, 0.0];
        let keys = [(0, start), (899, finish)].into_iter().map(|(frame, value)| {
            let mut key = Keyframe::new(FrameRate::FPS_30.tick_of(frame), Value::Vec3(value));
            key.in_interp = Interp::Linear;
            key.out_interp = Interp::Linear;
            key.spatial_auto = false;
            key
        }).collect();
        let position = layer.props.prop_mut("transform/position").ok_or("Missing moving track")?;
        position.value = Value::Vec3(start);
        position.keys = keys;
        layers.push(layer);
    }
    let mut nested = build::layer(&mut project, &comp, "Nested comp", LayerSource::Comp { item: inner_id }, (160, 90), None);
    set_position(&mut nested, [1750.0, 960.0, 0.0])?;
    layers.push(nested);
    layers.push(solid(&mut project, &comp, "Black background", [0.0; 3], (1920, 1080)));
    project.comp_mut(comp_id).ok_or("Missing root comp")?.layers = layers.into();
    Ok((project, comp_id))
}

fn verify_pixels(pixels: &[u8], frame: i64) -> Result<()> {
    let fraction = frame as f64 / 899.0;
    let x = (90.0 + 45.0 * fraction).round() as usize;
    let y = (100.0 + 20.0 * fraction).round() as usize;
    for (x, y, expected) in [
        (0, 0, [0, 0, 0, 255]),
        (x, y, [255, 0, 0, 255]),
        (1700, 935, [0, 255, 0, 255]),
    ] {
        let at = (y * 1920 + x) * 4;
        if pixels.get(at..at + 4) != Some(expected.as_slice()) {
            return Err(format!("Unexpected pixel at {x},{y}, frame {frame}").into());
        }
    }
    Ok(())
}

fn run() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let [_, mode, count, directory] = args.as_slice() else { return Err("Expected mode, layer count and private directory".into()); };
    let count: usize = count.parse()?;
    if ![3, 40, 80].contains(&count) || !["fresh", "warm", "sequence"].contains(&mode.as_str()) {
        return Err("Unsupported fixed stress case".into());
    }
    if mode == "sequence" && count != 80 {
        return Err("Full sequence is fixed to the 80-layer case".into());
    }
    let directory = Path::new(directory).canonicalize()?;
    let start = Instant::now();
    let (project, comp_id) = fixture(count)?;
    let serialized = project.to_file_json()?;
    fs::File::create_new(directory.join("project.ecproj"))?.write_all(serialized.as_bytes())?;
    let (reopened, repairs) = Project::from_json_repaired(&fs::read_to_string(directory.join("project.ecproj"))?)?;
    if project != reopened || !repairs.is_empty() {
        return Err("Stress project changed on reopen".into());
    }
    let setup_ms = start.elapsed().as_secs_f64() * 1000.0;
    let renderer = Renderer::new(&reopened, &NoFootage, RenderOpts::default());
    let iterations = if mode == "warm" { 11 } else { 1 };
    let frames = if mode == "sequence" { (0..900).collect::<Vec<_>>() } else { SAMPLES.to_vec() };
    let mut runs = Vec::new();
    for iteration in 0..iterations {
        let mut render_ms = 0.0;
        let mut rgba_hash_ms = 0.0;
        let mut png_ms = 0.0;
        let mut hashes = Vec::new();
        for frame in &frames {
            let start = Instant::now();
            let image = renderer.comp_frame(comp_id, FrameRate::FPS_30.tick_of(*frame));
            render_ms += start.elapsed().as_secs_f64() * 1000.0;
            if (image.width, image.height) != (1920, 1080) {
                return Err("Unexpected output dimensions".into());
            }
            let start = Instant::now();
            let pixels = image.to_rgba8();
            verify_pixels(&pixels, *frame)?;
            hashes.push(format!("{:x}", Sha256::digest(&pixels)));
            rgba_hash_ms += start.elapsed().as_secs_f64() * 1000.0;
            if mode == "sequence" || iteration == 0 {
                let start = Instant::now();
                let file = fs::File::create_new(directory.join(format!("frame-{frame:04}.png")))?;
                image::codecs::png::PngEncoder::new(file)
                    .write_image(&pixels, 1920, 1080, image::ExtendedColorType::Rgba8)?;
                png_ms += start.elapsed().as_secs_f64() * 1000.0;
            }
        }
        runs.push(json!({"iteration": iteration, "excluded_warmup": mode == "warm" && iteration == 0,
            "render_ms": render_ms, "rgba_hash_ms": rgba_hash_ms, "png_write_ms": png_ms,
            "frame_rgba_sha256": hashes}));
    }
    let report = json!({"mode": mode, "root_layers": count, "nested_layers": 3,
        "width": 1920, "height": 1080, "fps": 30, "duration_frames": 900, "frames": frames,
        "setup_save_reopen_ms": setup_ms, "project_sha256": format!("{:x}", Sha256::digest(serialized.as_bytes())),
        "project_roundtrip_equal": true, "pixel_probes_passed": true, "runs": runs});
    fs::File::create_new(directory.join("worker-report.json"))?
        .write_all(&serde_json::to_vec_pretty(&report)?)?;
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
