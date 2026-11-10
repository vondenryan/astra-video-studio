//! Fixed EC-0 text/curve cases only; no generic scene or command interface.
#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]
use effectcraft_color::Label;
use effectcraft_keyframe::{self as keys, Ease, Interp, Keyframe, TextDoc, Value};
use effectcraft_project::{build, Comp, ItemId, ItemKind, Layer, LayerSource, Project, Solid};
use effectcraft_render::{NoFootage, RenderOpts, Renderer};
use effectcraft_text::{fonts, layout_doc};
use effectcraft_time::{FrameRate, Tick};
use image::ImageEncoder;
use serde_json::{json, Value as Json};
use sha2::{Digest, Sha256};
use std::{fs::{self, File, OpenOptions}, io::Write, path::{Path, PathBuf}, process::ExitCode};

const REV: &str = "a41ff5015c6687db15a6f074a47b870b8f09fece";
const FONT_SHA: &str = "40d692fce188e4471e2b3cba937be967878f631ad3ebbbdcd587687c7ebe0c82";
const TITLE: &str = "AÇÃO COM PROPÓSITO";
const BODY: &str = "Texto em caixa.\nCurvas com movimento suave.";
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn exclusive(path: &Path) -> Result<File> {Ok(OpenOptions::new().write(true).create_new(true).open(path)?)}
fn put_json(path: &Path, value: &Json) -> Result<()> {Ok(exclusive(path)?.write_all(&serde_json::to_vec_pretty(value)?)?)}
fn tick(frame: i64) -> Tick {FrameRate::FPS_30.tick_of(frame)}

fn arguments(args: &[String]) -> Result<(PathBuf,String,String)> {
    if args.len()!=7 || args.get(1).map(String::as_str)!=Some("--root") || args.get(3).map(String::as_str)!=Some("--job") || args.get(5).map(String::as_str)!=Some("--case") {
        return Err("ARGUMENTS: --root <private root> --job <32 lowercase hex> --case <fixed case>".into());
    }
    let root=Path::new(args.get(2).ok_or("ROOT")?).canonicalize()?;
    let job=args.get(4).ok_or("JOB")?;
    let case=args.get(6).ok_or("CASE")?;
    if !root.is_dir() || job.len()!=32 || !job.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)) {return Err("INVALID_JOB".into());}
    if !["text-curves","missing-font","unsupported-glyph","wrong-font-hash"].contains(&case.as_str()) {return Err("UNSUPPORTED_CASE".into());}
    Ok((root.join(job),job.clone(),case.clone()))
}

fn strict_font(name: &str, text: &str, expected: &str) -> Result<fonts::FaceId> {
    let candidates: Vec<_>=fonts::all_faces().into_iter().filter(|f| f.info.postscript.as_deref()==Some(name)).collect();
    if candidates.len()!=1 {return Err("FONT_MISSING: exact PostScript identity absent or ambiguous".into());}
    let face=candidates.first().ok_or("FONT_MISSING")?;
    let fonts::FaceData::Static(bytes)=&face.info.data else {return Err("FONT_ORIGIN: only pinned bundled bytes accepted".into());};
    if face.info.origin!="bundled" || format!("{:x}",Sha256::digest(bytes))!=expected {return Err("FONT_HASH_MISMATCH".into());}
    if text.chars().any(|c| c!='\n' && !face.has_char(c)) {return Err("GLYPH_UNSUPPORTED: no per-character fallback allowed".into());}
    let resolved=fonts::resolve(name,"Regular");
    if resolved.missing || resolved.face!=face.id || resolved.synth_bold || resolved.synth_italic {return Err("FONT_SUBSTITUTION".into());}
    Ok(face.id)
}

fn checked_layout(doc: &TextDoc) -> Result<Json> {
    let face=strict_font(&doc.font,&doc.text,FONT_SHA)?;
    let layout=layout_doc(doc);
    if layout.layout.missing_font || layout.layout.glyphs.is_empty() || layout.layout.glyphs.iter().any(|g| g.face!=face || g.id==0 || g.synth_bold || g.synth_italic) {return Err("LAYOUT_SUBSTITUTION".into());}
    if let Some(size)=doc.box_size {
        if layout.bounds[0]<0.0 || layout.bounds[1]<0.0 || layout.bounds[2]>size[0] || layout.bounds[3]>size[1] || f64::from(layout.layout.bounds[3])>size[1] {return Err(format!("TEXT_OVERFLOW: ink {:?}, logical {:?}, box {:?}",layout.bounds,layout.layout.bounds,size).into());}
    }
    Ok(json!({"text":doc.text,"font":doc.font,"face_id":face,"glyphs":layout.layout.glyphs.len(),"lines":layout.lines,
        "bounds":layout.bounds,"missing_font":false,"all_glyph_faces_exact":true,"byte_of_char":layout.byte_of_char,
        "styles":layout.styles,"style_range_codepoints":[0,4]}))
}

fn scalar(interp: Interp) -> Vec<Keyframe> {
    [0,60].into_iter().map(|frame| {
        let mut key=Keyframe::new(tick(frame),Value::Scalar(if frame==0 {0.0} else {100.0}));
        key.in_interp=interp;key.out_interp=interp;key.spatial_auto=false;
        if interp==Interp::Bezier {key.in_ease=vec![Ease::EASY];key.out_ease=vec![Ease::EASY];}
        key
    }).collect()
}

fn spatial() -> Vec<Keyframe> {
    [(0,[100.0,300.0,0.0],[0.0,0.0,0.0],[0.0,-40.0,0.0],0.0),
     (30,[320.0,240.0,0.0],[-100.0,0.0,0.0],[100.0,0.0,0.0],180.0),
     (60,[540.0,300.0,0.0],[0.0,-40.0,0.0],[0.0,0.0,0.0],0.0)].into_iter().map(|(f,v,i,o,s)| {
        let mut key=Keyframe::new(tick(f),Value::Vec3(v));
        key.spatial_auto=false;key.spatial_in=i;key.spatial_out=o;
        key.in_interp=Interp::Bezier;key.out_interp=Interp::Bezier;
        key.in_ease=vec![Ease{speed:s,influence:1.0/3.0}];key.out_ease=key.in_ease.clone();key
    }).collect()
}

fn set_position(layer: &mut Layer, value: [f64;3]) -> Result<()> {
    layer.props.prop_mut("transform/position").ok_or("POSITION_ABSENT")?.value=Value::Vec3(value);Ok(())
}

fn fixture() -> Result<(Project,ItemId,Json)> {
    let mut point=TextDoc {text:TITLE.into(),font:"Inter-Regular".into(),size:36.0,leading:Some(42.0),..Default::default()};
    point.apply_style(0..4,|s| s.fill=[0.4,0.9,1.0,1.0]);
    if point.style_at(3).fill==point.style_at(4).fill {return Err("UNICODE_STYLE_RANGE".into());}
    let body=TextDoc {text:BODY.into(),font:"Inter-Regular".into(),size:24.0,leading:Some(30.0),baseline_shift:-2.0,box_size:Some([500.0,90.0]),..Default::default()};
    let layouts=json!({"point":checked_layout(&point)?,"box":checked_layout(&body)?});
    let mut project=Project::default();
    let comp=Comp::new(640,360,FrameRate::FPS_30,tick(61));
    let cid=project.add_item("EC0 text and curves",Label::Sandstone,None,ItemKind::Comp(comp.clone().into()));
    let mut title=build::layer(&mut project,&comp,"Point text",LayerSource::Text,(0,0),None);
    set_position(&mut title,[40.0,75.0,0.0])?;
    title.props.prop_mut("text/sourceText").ok_or("SOURCE_TEXT_ABSENT")?.value=Value::Text(Box::new(point));
    let mut paragraph=build::layer(&mut project,&comp,"Box text",LayerSource::Text,(0,0),None);
    set_position(&mut paragraph,[40.0,100.0,0.0])?;
    paragraph.props.prop_mut("text/sourceText").ok_or("SOURCE_TEXT_ABSENT")?.value=Value::Text(Box::new(body));
    let solid=project.add_item("Original moving solid",Label::Aqua,None,ItemKind::Solid(Solid{color:[0.4,0.9,1.0],width:20,height:20,pixel_aspect:1.0}));
    let mut dot=build::layer(&mut project,&comp,"Curved passage",LayerSource::Solid{item:solid},(20,20),None);
    dot.props.prop_mut("transform/position").ok_or("POSITION_ABSENT")?.keys=spatial();
    dot.props.prop_mut("transform/opacity").ok_or("OPACITY_ABSENT")?.keys=scalar(Interp::Bezier);
    let mut probes=build::layer(&mut project,&comp,"Scalar diagnostics",LayerSource::Null,(100,100),None);
    probes.props.prop_mut("transform/opacity").ok_or("OPACITY_ABSENT")?.keys=scalar(Interp::Linear);
    probes.props.prop_mut("transform/rotation").ok_or("ROTATION_ABSENT")?.keys=scalar(Interp::Hold);
    let bg=project.add_item("Original background",Label::Sandstone,None,ItemKind::Solid(Solid{color:[0.0,0.0,0.0],width:640,height:360,pixel_aspect:1.0}));
    let background=build::layer(&mut project,&comp,"Background",LayerSource::Solid{item:bg},(640,360),None);
    let target=project.comp_mut(cid).ok_or("COMP_ABSENT")?;
    for layer in [title,paragraph,dot,probes,background] {target.layers.push(layer);}
    Ok((project,cid,layouts))
}

fn evaluated(keys: &[Keyframe], time: Tick, spatial: bool) -> Result<Json> {
    Ok(serde_json::to_value(keys::evaluate(keys,time,spatial).ok_or("EVALUATION_ABSENT")?)?)
}

fn run(args: &[String]) -> Result<Json> {
    let (directory,job,case)=arguments(args)?;
    match case.as_str() {
        "missing-font"=>{strict_font("AstraDefinitelyMissing-EC0",TITLE,FONT_SHA)?;return Err("NEGATIVE_NOT_REJECTED".into());},
        "unsupported-glyph"=>{strict_font("Inter-Regular","\u{10ffff}",FONT_SHA)?;return Err("NEGATIVE_NOT_REJECTED".into());},
        "wrong-font-hash"=>{strict_font("Inter-Regular",TITLE,&"0".repeat(64))?;return Err("NEGATIVE_NOT_REJECTED".into());},
        _=>{},
    }
    // Font/layout failures occur before the exclusive output slot is created.
    let (project,cid,layouts)=fixture()?;
    fs::create_dir(&directory)?;
    exclusive(&directory.join("project.ecproj"))?.write_all(project.to_file_json()?.as_bytes())?;
    let (reopened,repairs)=Project::from_json_repaired(&fs::read_to_string(directory.join("project.ecproj"))?)?;
    if project!=reopened || !repairs.is_empty() {return Err("ROUNDTRIP_MISMATCH".into());}
    let comp=reopened.comp(cid).ok_or("COMP_ABSENT")?;
    let dot=comp.layers.iter().find(|l| l.name=="Curved passage").ok_or("DOT_ABSENT")?;
    let diagnostic=comp.layers.iter().find(|l| l.name=="Scalar diagnostics").ok_or("PROBES_ABSENT")?;
    let linear=&diagnostic.props.prop("transform/opacity").ok_or("TRACK_ABSENT")?.keys;
    let hold=&diagnostic.props.prop("transform/rotation").ok_or("TRACK_ABSENT")?.keys;
    let bezier=&dot.props.prop("transform/opacity").ok_or("TRACK_ABSENT")?.keys;
    let path=&dot.props.prop("transform/position").ok_or("TRACK_ABSENT")?.keys;
    let samples=(-1..=61).map(|frame| Ok(json!({"frame":frame,"linear":evaluated(linear,tick(frame),false)?,
        "hold":evaluated(hold,tick(frame),false)?,"bezier":evaluated(bezier,tick(frame),false)?,"position":evaluated(path,tick(frame),true)?}))).collect::<Result<Vec<_>>>()?;
    let mut timing=Vec::new();
    for stretch in [100.0,200.0,-100.0] {
        let mut layer=dot.clone();layer.start_time=tick(10);layer.stretch=stretch;
        for frame in [10,20,50] {let local=layer.layer_time(tick(frame));timing.push(json!({"stretch":stretch,"comp_frame":frame,"local_ticks":local.0,"inverse_comp_ticks":layer.comp_time(local).0}));}
    }
    let mut frame_ticks=Vec::new();
    for rate in [FrameRate::FPS_30,FrameRate::new(24000,1001)] {
        for frame in [-30,-1,0,1,2,59,60,30000] {let time=rate.tick_of(frame);frame_ticks.push(json!({"num":rate.num,"den":rate.den,"frame":frame,"ticks":time.0,"roundtrip_frame":rate.frame_at(time)}));}
    }
    let join=[-0.0001,0.0,0.0001].into_iter().map(|dt| Ok(json!({"dt":dt,"position":evaluated(path,Tick::from_seconds_f64(1.0+dt),true)?}))).collect::<Result<Vec<_>>>()?;
    put_json(&directory.join("curves.json"),&json!({"samples":samples,"linear_keys":linear,"hold_keys":hold,"bezier_keys":bezier,"path_keys":path,"join_probes":join,"timing":timing,"frame_ticks":frame_ticks}))?;
    put_json(&directory.join("text.json"),&layouts)?;
    let renderer=Renderer::new(&reopened,&NoFootage,RenderOpts::default());
    for frame in 0..61 {
        let image=renderer.comp_frame(cid,tick(frame));
        if image.width!=640 || image.height!=360 {return Err("RENDER_DIMENSIONS".into());}
        image::codecs::png::PngEncoder::new(exclusive(&directory.join(format!("frame-{frame:04}.png")))?)
            .write_image(&image.to_rgba8(),640,360,image::ExtendedColorType::Rgba8)?;
    }
    if fonts::system_scanned() {return Err("SYSTEM_FONT_SCAN_FORBIDDEN".into());}
    let result=json!({"protocol":"astra-ec0-text-curves-v1","upstream_revision":REV,"job_id":job,"case":case,"status":"succeeded", "width":640,"height":360,"fps":30,"frame_count":61,
        "font_postscript":"Inter-Regular","font_sha256":FONT_SHA,"project_roundtrip_equal":true,"font_preflight_passed":true,"system_fonts_scanned":false,
        "scope":"Fixed text and manual curves; independent oracle validation required; no AE parity"});
    put_json(&directory.join("result.json"),&result)?;Ok(result)
}

fn main() -> ExitCode {
    let args: Vec<String>=std::env::args().collect();
    let (value,code)=match run(&args) {Ok(v)=>(v,ExitCode::SUCCESS),Err(e)=>(json!({"protocol":"astra-ec0-text-curves-v1","job_id":args.get(4),"case":args.get(6),"status":"failed","error":e.to_string().chars().take(1200).collect::<String>(),"system_fonts_scanned":fonts::system_scanned()}),ExitCode::FAILURE)};
    match serde_json::to_vec(&value) {Ok(mut bytes)=>{bytes.push(b'\n');if std::io::stdout().lock().write_all(&bytes).is_err() {return ExitCode::FAILURE;}},Err(_)=>return ExitCode::FAILURE,}
    code
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    #[test]
    fn exact_font_rejects_substitution_hash_and_missing_character() {
        assert!(strict_font("Inter-Regular",TITLE,FONT_SHA).is_ok());
        assert!(strict_font("NotTheFont",TITLE,FONT_SHA).is_err());
        assert!(strict_font("Inter-Regular",TITLE,"bad").is_err());
        assert!(strict_font("Inter-Regular","\u{10ffff}",FONT_SHA).is_err());
        assert!(!fonts::system_scanned());
    }
    #[test]
    fn unicode_styles_and_manual_keys_survive_roundtrip() {
        let (project,_,_)=fixture().unwrap();
        let (reopened,repairs)=Project::from_json_repaired(&project.to_file_json().unwrap()).unwrap();
        assert_eq!(project,reopened);assert!(repairs.is_empty());
        for key in spatial() {assert!(!key.spatial_auto && !key.auto_bezier && !key.continuous && !key.spatial_continuous && !key.roving);}
    }
}
