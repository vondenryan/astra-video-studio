//! Fixed synthetic CPU fixture only. Not a general executor or an Astra backend.
#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

use effectcraft_color::Label;
use effectcraft_project::{build, Comp, ItemKind, LayerSource, Project, Solid};
use effectcraft_render::{NoFootage, RenderOpts, Renderer};
use effectcraft_time::{FrameRate, Tick};
use image::ImageEncoder;
use serde_json::{json, Value};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const REVISION: &str = "a41ff5015c6687db15a6f074a47b870b8f09fece";
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn exclusive_file(path: &Path) -> Result<File> {
    Ok(OpenOptions::new().write(true).create_new(true).open(path)?)
}

fn job_path(args: &[String]) -> Result<(PathBuf, String)> {
    if args.len() != 5 || args.get(1).map(String::as_str) != Some("--root")
        || args.get(3).map(String::as_str) != Some("--job") {
        return Err("Usage: astra-ec0-probe --root <existing private root> --job <32 lowercase hex>".into());
    }
    let root = Path::new(args.get(2).ok_or("Missing root")?).canonicalize()?;
    let job = args.get(4).ok_or("Missing job ID")?;
    if !root.is_dir() || job.len() != 32 || !job.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)) {
        return Err("Invalid root or job ID".into());
    }
    Ok((root.join(job), job.clone()))
}

fn fixture() -> Result<(Project, effectcraft_project::ItemId)> {
    let mut project = Project::default();
    let comp = Comp::new(160, 90, FrameRate::FPS_30, Tick::from_seconds_f64(0.2));
    let comp_id = project.add_item("EC0 synthetic CPU fixture", Label::Sandstone, None, ItemKind::Comp(comp.clone().into()));
    let red_id = project.add_item("Original red solid", Label::Aqua, None,
        ItemKind::Solid(Solid {color: [1.0,0.0,0.0], width:64, height:24, pixel_aspect:1.0}));
    let black_id = project.add_item("Original black solid", Label::Aqua, None,
        ItemKind::Solid(Solid {color: [0.0,0.0,0.0], width:160, height:90, pixel_aspect:1.0}));
    let foreground = build::layer(&mut project, &comp, "Foreground", LayerSource::Solid {item:red_id}, (64,24), None);
    let background = build::layer(&mut project, &comp, "Background", LayerSource::Solid {item:black_id}, (160,90), None);
    let target = project.comp_mut(comp_id).ok_or("Created composition absent")?;
    target.layers.push(foreground);
    target.layers.push(background);
    Ok((project, comp_id))
}

fn run(args: &[String]) -> Result<Value> {
    let (directory, job) = job_path(args)?;
    // Exclusive attempt slot: preserve every old/partial run instead of replaying.
    fs::create_dir(&directory)?;
    let (project, comp_id) = fixture()?;
    let source = project.to_file_json()?;
    exclusive_file(&directory.join("project.ecproj"))?.write_all(source.as_bytes())?;
    let persisted = fs::read_to_string(directory.join("project.ecproj"))?;
    let (reopened, repairs) = Project::from_json_repaired(&persisted)?;
    if project != reopened || !repairs.is_empty() {return Err("Project roundtrip changed state".into());}
    let renderer = Renderer::new(&reopened, &NoFootage, RenderOpts::default());
    for frame in 0..6 {
        let image = renderer.comp_frame(comp_id, Tick::from_seconds_f64(f64::from(frame)/30.0));
        if image.width != 160 || image.height != 90 {return Err("Unexpected render dimensions".into());}
        let pixels = image.to_rgba8();
        let center = pixels.get((45*160+80)*4..(45*160+80)*4+4).ok_or("Missing center pixel")?;
        let corner = pixels.get(0..4).ok_or("Missing corner pixel")?;
        if center != [255,0,0,255] || corner != [0,0,0,255] {return Err("Unexpected fixture pixels/stacking".into());}
        let file = exclusive_file(&directory.join(format!("frame-{frame:04}.png")))?;
        image::codecs::png::PngEncoder::new(file).write_image(&pixels,160,90,image::ExtendedColorType::Rgba8)?;
    }
    let result = json!({"protocol":"astra-ec0-v1","job_id":job,"status":"succeeded",
        "upstream_revision":REVISION,"backend":"effectcraft-cpu","width":160,"height":90,
        "fps":30,"frame_count":6,"project_roundtrip_equal":true,"pixel_probes_passed":true,
        "scope":"Fixed opaque solids only; no font, curve, AE parity, alpha or production acceptance"});
    exclusive_file(&directory.join("result.json"))?.write_all(&serde_json::to_vec_pretty(&result)?)?;
    Ok(result)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    let (value, code) = match run(&args) {
        Ok(value) => (value, ExitCode::SUCCESS),
        Err(error) => (json!({"protocol":"astra-ec0-v1","status":"failed","error":error.to_string().chars().take(1200).collect::<String>()}), ExitCode::FAILURE),
    };
    match serde_json::to_vec(&value) {
        Ok(mut bytes) => {
            bytes.push(b'\n');
            if std::io::stdout().lock().write_all(&bytes).is_err() {return ExitCode::FAILURE;}
        },
        Err(_) => return ExitCode::FAILURE,
    }
    code
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    #[test]
    fn job_names_cannot_escape_or_reuse_arbitrary_paths() {
        let root = std::env::current_dir().unwrap().to_string_lossy().to_string();
        for value in ["../escape", "A123", "a/../../x", "a".repeat(33).as_str()] {
            assert!(job_path(&["probe".into(),"--root".into(),root.clone(),"--job".into(),value.into()]).is_err());
        }
        assert!(job_path(&["probe".into(),"--root".into(),root,"--job".into(),"a".repeat(32)]).is_ok());
    }
    #[test]
    fn synthetic_project_roundtrips_without_repair() {
        let (project, _) = fixture().unwrap();
        let (reopened, repairs) = Project::from_json_repaired(&project.to_file_json().unwrap()).unwrap();
        assert_eq!(project,reopened);assert!(repairs.is_empty());
    }
}
