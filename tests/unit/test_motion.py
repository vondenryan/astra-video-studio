import copy
import math
import pytest
from pydantic import ValidationError

from astra_video_studio.motion_engine.easing import evaluate
from astra_video_studio.motion_engine.schemas import MotionRequest, TransformValues
from astra_video_studio.motion_engine.skills import plan
from astra_video_studio.motion_engine.timeline import frame, track
from astra_video_studio.motion_engine.service import find_target, values_match, verify_edit

IDS = dict(project_id="1" * 32, composition_id="2" * 32, layer_id="3" * 32)
COMP = dict(width=1920, height=1080, fps=30, duration=10)
LAYER = dict(position=[960, 540, 0], in_point=0, out_point=10, transforms={})


@pytest.mark.parametrize("name", ["linear", "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic"])
def test_easing_endpoints_monotonic_and_symmetry(name):
    values = [evaluate(name, i / 100) for i in range(101)]
    assert values[0] == 0 and values[-1] == 1
    assert values == sorted(values)
    if name == "ease_in_out_cubic":
        assert evaluate(name, 0.25) == pytest.approx(0.0625)
        assert evaluate(name, 0.75) == pytest.approx(0.9375)


@pytest.mark.parametrize("skill,params,property_name", [("slide_in", {}, "position"), ("scale_pop", {}, "scale"), ("fade_in_out", {"fade_in": 0.6, "fade_out": 0.8}, "opacity"), ("smooth_zoom", {}, "scale")])
def test_every_skill_generates_frame_aligned_native_keys(skill, params, property_name):
    request = MotionRequest(**IDS, skill=skill, start_time=0, duration=3, params=params)
    result = plan(request, COMP, LAYER)
    assert result["tracks"][0]["property"] == property_name
    keys = result["tracks"][0]["keys"]
    assert keys[0]["time"] == 0 and keys[-1]["time"] == 3
    assert all(math.isclose(k["time"] * 30, round(k["time"] * 30), abs_tol=1e-8) for k in keys)
    assert all(keys[i]["time"] < keys[i + 1]["time"] for i in range(len(keys) - 1))


def test_slide_relative_coordinates_and_overshoot():
    request = MotionRequest(**IDS, skill="slide_in", duration=1)
    keys = plan(request, COMP, LAYER)["tracks"][0]["keys"]
    assert keys[0]["value"][0] == pytest.approx(960 - 1920 * 0.24)
    assert max(k["value"][0] for k in keys) == pytest.approx(960 + 1920 * 0.24 * 0.06)
    assert keys[-1]["value"] == [960, 540]


def test_fade_holds_and_exits_without_overlap():
    request = MotionRequest(**IDS, skill="fade_in_out", duration=10)
    keys = plan(request, COMP, LAYER)["tracks"][0]["keys"]
    assert keys[0]["value"] == [0] and keys[-1]["value"] == [0]
    assert [k["value"] for k in keys if k["time"] in (0.6, 9.2)] == [[100], [100]]
    with pytest.raises(ValueError, match="overlap"):
        plan(MotionRequest(**IDS, skill="fade_in_out", duration=1), COMP, LAYER)


def test_exact_cubic_tangents_and_spatial_dimensions():
    keys = track("opacity", [(0, [0]), (1, [100])], ["ease_out_cubic"], 30)["keys"]
    assert keys[0]["out_speed"] == [300]
    assert keys[-1]["in_speed"] == [0]
    keys = track("position", [(0, [0, 0]), (1, [300, 400])], ["ease_in_cubic"], 30)["keys"]
    assert keys[-1]["in_speed"] == [1500]
    assert len(keys[0]["out_speed"]) == 1
    keys = track("scale", [(0, [100, 100]), (1, [110, 110])], ["ease_in_out_cubic"], 30)["keys"]
    assert len(keys) == 3 and keys[1]["time"] == 0.5
    assert keys[1]["in_speed"] == [30, 30] == keys[1]["out_speed"]


def test_odd_frame_easing_preserves_continuous_midpoint_velocity():
    keys = track("opacity", [(0, [100]), (7 / 30, [0])], ["ease_in_out_cubic"], 30)["keys"]
    assert keys[1]["in_speed"] == pytest.approx(keys[1]["out_speed"])
    assert keys[1]["time"] == 4 / 30


@pytest.mark.parametrize("params", [{"duration": 0.001}, {"start_time": 10, "duration": 1}, {"duration": 1 / 30}])
def test_invalid_or_too_short_timeline(params):
    with pytest.raises(ValueError):
        plan(MotionRequest(**IDS, skill="slide_in", **params), COMP, LAYER)


def test_existing_animation_and_expression_are_protected():
    layer = copy.deepcopy(LAYER)
    layer["transforms"]["scale"] = {"keys": [{"time": 0.3}, {"time": 1}], "expression_enabled": False}
    with pytest.raises(ValueError, match="overlaps"):
        plan(MotionRequest(**IDS, skill="smooth_zoom", duration=2), COMP, layer)
    result = plan(MotionRequest(**IDS, skill="smooth_zoom", start_time=2, duration=4), COMP, layer)
    assert result["start_time"] == 2
    layer["transforms"]["scale"]["expression_enabled"] = True
    with pytest.raises(ValueError, match="expression"):
        plan(MotionRequest(**IDS, skill="smooth_zoom", start_time=2, duration=4), COMP, layer)


@pytest.mark.parametrize("fields", [{"skill": "arbitrary_skill"}, {"skill": "slide_in", "params": {"execute_jsx": "quit()"}}, {"skill": "scale_pop", "params": {"overshoot": 1}}, {"skill": "slide_in", "params": {"distance_px": float("inf")}}, {"skill": "smooth_zoom", "duration": float("nan")}, {"skill": "fade_in_out", "project_id": "../x"}])
def test_motion_schema_rejects_invalid_parameters(fields):
    with pytest.raises(ValidationError):
        MotionRequest(**(IDS | fields))


@pytest.mark.parametrize("values", [{}, {"opacity": 101}, {"scale": [0, 100]}, {"position": [0, float("nan")]}, {"rotation": float("inf")}, {"anchor": [100001, 0]}])
def test_transform_limits(values):
    with pytest.raises(ValidationError):
        TransformValues(**values)


def test_frame_rounding_and_invalid_fps():
    assert frame(0.65, 30) == 20
    with pytest.raises(ValueError):
        frame(1, 0)
    assert values_match([960, 540, 0], [960, 540])
    assert not values_match([960], [960, 540])


def test_targets_must_be_unique():
    with pytest.raises(ValueError):
        find_target({"compositions": []}, "x", "y")


def test_postsave_verifier_rejects_unrelated_edits():
    before = {"compositions": [{"composition_id": "astra:composition:" + IDS["composition_id"], **COMP, "layers": [{"layer_id": "astra:layer:" + IDS["layer_id"], "text": "ASTRA", "transforms": {"opacity": {"value": 100, "keys": []}, "rotation": {"value": 0, "keys": []}}}]}]}
    after = copy.deepcopy(before)
    after["compositions"][0]["layers"][0]["transforms"]["rotation"]["value"] = 15
    with pytest.raises(ValueError, match="Unrelated"):
        verify_edit(before, after, IDS["composition_id"], IDS["layer_id"], {"opacity": 80}, False)
