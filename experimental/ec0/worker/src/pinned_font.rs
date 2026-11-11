use effectcraft_text::fonts;
use sha2::{Digest, Sha256};

pub fn strict_font(name: &str, text: &str, expected: &str) -> Result<fonts::FaceId, Box<dyn std::error::Error>> {
    let candidates: Vec<_> = fonts::all_faces().into_iter()
        .filter(|face| face.info.postscript.as_deref() == Some(name))
        .collect();
    let [face] = candidates.as_slice() else {
        return Err("FONT_MISSING: exact PostScript identity absent or ambiguous".into());
    };
    let fonts::FaceData::Static(bytes) = &face.info.data else {
        return Err("FONT_ORIGIN: only pinned bundled bytes accepted".into());
    };
    if face.info.origin != "bundled" || format!("{:x}", Sha256::digest(bytes)) != expected {
        return Err("FONT_HASH_MISMATCH".into());
    }
    if text.chars().any(|character| character != '\n' && !face.has_char(character)) {
        return Err("GLYPH_UNSUPPORTED: no per-character fallback allowed".into());
    }
    let resolved = fonts::resolve(name, "Regular");
    if resolved.missing || resolved.face != face.id || resolved.synth_bold || resolved.synth_italic {
        return Err("FONT_SUBSTITUTION".into());
    }
    Ok(face.id)
}
