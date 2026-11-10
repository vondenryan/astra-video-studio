"""Sidecar IDs for existing projects; never overwrite user comments."""
import copy
from uuid import uuid4

from astra_video_studio.project_manager import valid_id


def build_id_map(data: dict, previous: dict | None = None, preserve_comments: bool = False) -> dict:
    result = copy.deepcopy(previous) if previous else {"compositions": {}, "layers": {}}
    for group, objects in (("compositions", data["compositions"]), ("layers", [l for c in data["compositions"] for l in c["layers"]])):
        seen_native, seen_ids = set(), set()
        field = "composition_id" if group == "compositions" else "layer_id"
        prefix = "astra:composition:" if group == "compositions" else "astra:layer:"
        for obj in objects:
            native = obj["ae_id"]
            if type(native) is not int or native < 1 or native in seen_native:
                raise ValueError("Missing/duplicate native AE identity")
            seen_native.add(native)
            key = str(native)
            chosen = result[group].get(key)
            if chosen is None and preserve_comments and obj.get(field, "").startswith(prefix):
                try:
                    candidate = valid_id(obj[field][len(prefix):])
                    chosen = candidate if candidate not in seen_ids and candidate not in result[group].values() else None
                except ValueError:
                    pass
            chosen = valid_id(chosen) if chosen else uuid4().hex
            if chosen in seen_ids:
                raise ValueError("Duplicate stable identity; refusing ambiguous mapping")
            seen_ids.add(chosen)
            result[group][key] = chosen
    return result


def extend_project_ids(manifest: dict, data: dict) -> dict:
    previous = manifest.get("id_map")
    if previous is None:
        # Seed from verified disk metadata, not current layer order. A newly
        # duplicated layer may precede its original and share the same comment.
        previous = build_id_map(manifest["result"]["data"], preserve_comments=True)
    return build_id_map(data, previous, preserve_comments=True)


def mapped_state(data: dict, mapping: dict) -> dict:
    result = copy.deepcopy(data)
    for comp in result["compositions"]:
        comp["composition_id"] = "astra:composition:" + mapping["compositions"][str(comp["ae_id"])]
        for layer in comp["layers"]:
            layer["layer_id"] = "astra:layer:" + mapping["layers"][str(layer["ae_id"])]
    return result
