"""Only fixed, reviewed JSX operations. All variable content is JSON data."""
import json
from pathlib import Path


def render_script(action: str, payload: dict) -> str:
    if action not in {"create", "inspect", "snapshot", "motion", "transform", "open_copy", "save_version", "effect", "mask", "preview_prepare", "batch_motion", "scene_build", "storyboard_build", "dependencies_inspect", "layer_add", "layers_add", "asset_import", "scene_edit", "design_edit", "design_fonts", "animation_edit", "revision_edit", "version_restore", 'delivery_inspect', 'delivery_collect', 'delivery_validate'}:
        raise ValueError("Unknown trusted AE action")
    source = (Path(__file__).parent / "scripts" / "project.jsx").read_text(encoding="utf-8")
    source = source.replace('/*ASTRA_SCENE_OPERATIONS*/', (Path(__file__).parent / 'scripts' / 'scene_ops.jsx').read_text(encoding='utf-8'))
    source = source.replace('/*ASTRA_DESIGN_OPERATIONS*/', (Path(__file__).parent / 'scripts' / 'design_ops.jsx').read_text(encoding='utf-8'))
    source = source.replace('/*ASTRA_ANIMATION_OPERATIONS*/', (Path(__file__).parent / 'scripts' / 'animation_ops.jsx').read_text(encoding='utf-8'))
    source = source.replace('/*ASTRA_REVISION_OPERATIONS*/', (Path(__file__).parent / 'scripts' / 'revision_ops.jsx').read_text(encoding='utf-8'))
    source = source.replace('/*ASTRA_DELIVERY_OPERATIONS*/', (Path(__file__).parent / 'scripts' / 'delivery_ops.jsx').read_text(encoding='utf-8'))
    source = source.replace('/*ASTRA_LAYER_BATCH_OPERATIONS*/', (Path(__file__).parent / 'scripts' / 'layer_batch.jsx').read_text(encoding='utf-8'))
    return source.replace("/*ASTRA_INPUT*/null", json.dumps(dict(payload, action=action), ensure_ascii=True, allow_nan=False))
