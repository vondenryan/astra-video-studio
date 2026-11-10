from astra_video_studio.motion_engine.schemas import MotionRequest
from astra_video_studio.motion_engine.timeline import frame, track
from astra_video_studio.motion_engine.easing import evaluate
import math
import random


def plan(request: MotionRequest, composition: dict, layer: dict) -> dict:
    fps = composition["fps"]
    start_frame = frame(request.start_time, fps)
    end_frame = frame(request.start_time + request.duration, fps)
    if end_frame <= start_frame:
        raise ValueError("Animation must span at least one frame")
    start, end = start_frame / fps, end_frame / fps
    if start < layer["in_point"] - 1e-6 or end > min(composition["duration"], layer["out_point"]) + 1e-6:
        raise ValueError("Animation lies outside the composition/layer lifetime")
    params = request.params
    tracks = []
    if request.skill == 'anticipate_settle':
        if end_frame - start_frame < 10: raise ValueError('Anticipation/settlement needs at least 10 frames')
        target = layer['position'][:2]
        axis = 0 if params.direction in ('left', 'right') else 1
        sign = -1 if params.direction in ('left', 'up') else 1
        distance = params.distance_px if params.distance_px is not None else composition['width' if axis == 0 else 'height'] * params.distance_ratio
        initial, anticipation, peak = list(target), list(target), list(target)
        initial[axis] += sign * distance
        anticipation[axis] += sign * distance * (1 + params.anticipation_ratio)
        peak[axis] -= sign * distance * params.overshoot
        a = frame(start + (end - start) * 0.2, fps) / fps
        b = frame(start + (end - start) * 0.75, fps) / fps
        tracks.append(track('position', [(start, initial), (a, anticipation), (b, peak), (end, target)], ['ease_in_out_cubic', params.easing, 'ease_in_out_cubic'], fps))
    elif request.skill == "slide_in":
        target = layer["position"][:2]
        axis = 0 if params.direction in ("left", "right") else 1
        sign = -1 if params.direction in ("left", "up") else 1
        distance = params.distance_px if params.distance_px is not None else composition["width" if axis == 0 else "height"] * params.distance_ratio
        initial = list(target)
        initial[axis] += sign * distance
        points = [(start, initial), (end, target)]
        curves = [params.easing]
        if params.overshoot:
            peak = list(target)
            peak[axis] -= sign * distance * params.overshoot
            settle = max(start_frame + 1, min(end_frame - 2, frame(start + (end - start) * 0.75, fps))) / fps
            points = [(start, initial), (settle, peak), (end, target)]
            curves = [params.easing, "ease_in_out_cubic"]
        tracks.append(track("position", points, curves, fps))
    elif request.skill == "scale_pop":
        points = [(start, [params.initial_scale] * 2), (end, [params.final_scale] * 2)]
        curves = [params.easing]
        if params.overshoot:
            peak_time = max(start_frame + 1, min(end_frame - 2, frame(start + (end - start) * 0.75, fps))) / fps
            points.insert(1, (peak_time, [params.final_scale * (1 + params.overshoot)] * 2))
            curves.append("ease_in_out_cubic")
        tracks.append(track("scale", points, curves, fps))
    elif request.skill == "smooth_zoom":
        tracks.append(track("scale", [(start, [params.initial_scale] * 2), (end, [params.final_scale] * 2)], [params.easing], fps))
    elif request.skill == "parallax_2d":
        initial = layer["position"][:2]
        final = [initial[0] + composition["width"] * params.displacement[0] * params.depth, initial[1] + composition["height"] * params.displacement[1] * params.depth]
        tracks.append(track("position", [(start, initial), (end, final)], [params.easing], fps))
    elif request.skill == "shake":
        if params.frequency_hz > fps / 2:
            raise ValueError("Shake frequency exceeds frame-rate limit")
        rng = random.Random(params.seed)
        step = max(1, int(fps / (params.frequency_hz * 4)))
        points = [(start, layer["position"][:2])]
        for f in range(start_frame + step, end_frame, step):
            u = (f - start_frame) / (end_frame - start_frame)
            amplitude = params.amplitude_px * math.exp(-params.decay * u)
            points.append((f / fps, [v + rng.uniform(-amplitude, amplitude) for v in layer["position"][:2]]))
        points.append((end, layer["position"][:2]))
        tracks.append(track("position", points, ["linear"] * (len(points) - 1), fps))
    elif request.skill == "text_reveal":
        if layer.get("text") is None or not layer.get("bounds"):
            raise ValueError("Text reveal requires text bounds")
        b = layer["bounds"]
        x, y = b["left"] - params.padding_px, b["top"] - params.padding_px
        width, height = b["width"] + 2 * params.padding_px, b["height"] + 2 * params.padding_px
        if width <= 0 or height <= 0:
            raise ValueError("Text reveal has empty bounds")
        keys = []
        frames = sorted({start_frame, end_frame, *(frame(start + (end - start) * u, fps) for u in (0.25, 0.5, 0.75))})
        for f in frames:
            u = evaluate(params.easing, (f - start_frame) / (end_frame - start_frame))
            left, top, w, h = x, y, width, height
            if params.direction in ("left", "right"):
                w = max(0.01, width * u)
                if params.direction == "right": left = x + width - w
            else:
                h = max(0.01, height * u)
                if params.direction == "down": top = y + height - h
            keys.append({"time": f / fps, "vertices": [[left, top], [left + w, top], [left + w, top + h], [left, top + h]]})
        return {"skill": request.skill, "start_time": start, "end_time": end, "motion_blur": params.motion_blur, "tracks": [], "mask_reveal": {"keys": keys}}
    else:
        fade_in_end = (start_frame + frame(params.fade_in, fps)) / fps
        fade_out_start = (end_frame - frame(params.fade_out, fps)) / fps
        if fade_in_end <= start or fade_out_start >= end or fade_in_end > fade_out_start:
            raise ValueError("Fade intervals must span frames and fit without overlap")
        points = [(start, [0]), (fade_in_end, [100])]
        curves = [params.easing]
        if fade_out_start > fade_in_end:
            points.append((fade_out_start, [100]))
            curves.append("linear")
        points.append((end, [0]))
        curves.append(params.easing)
        tracks.append(track("opacity", points, curves, fps))
    for item in tracks:
        if len(item["keys"]) > 900:
            raise ValueError("Motion exceeds 900-key limit")
        existing = layer.get("transforms", {}).get(item["property"], {})
        if existing.get("separated") or not existing.get("available", True):
            raise ValueError("Separated or unsupported transform property")
        if existing.get("expression_enabled"):
            raise ValueError("Cannot animate a property with an enabled expression")
        keys = existing.get("keys", [])
        if keys and not (item["keys"][-1]["time"] < keys[0]["time"] - 1e-6 or item["keys"][0]["time"] > keys[-1]["time"] + 1e-6):
            raise ValueError("Animation overlaps an existing keyed interval; choose a different time or property")
    return {"skill": request.skill, "start_time": start, "end_time": end, "motion_blur": params.motion_blur, "tracks": tracks}
