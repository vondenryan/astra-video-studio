import math
from astra_video_studio.motion_engine.easing import slopes


def frame(time: float, fps: float) -> int:
    if not math.isfinite(time) or not math.isfinite(fps) or fps <= 0 or time < 0:
        raise ValueError("Time must be finite/nonnegative and FPS positive")
    return int(math.floor(time * fps + 0.5))


def track(property_name: str, points: list[tuple[float, list[float]]], easings: list[str], fps: float) -> dict:
    """Compile segments to native key values and cubic temporal ease velocities.

    Spatial position uses one nonnegative speed; nonspatial dimensions use
    independent signed velocities. Ease-in-out has two cubic segments.
    """
    expanded = [points[0]]
    curves = []
    for (a_time, a), (b_time, b), easing in zip(points[:-1], points[1:], easings, strict=True):
        if b_time <= a_time:
            raise ValueError("Keyframes must have strictly increasing times")
        if easing == "ease_in_out_cubic":
            mid_frame = frame((a_time + b_time) / 2, fps)
            mid_time = mid_frame / fps
            if mid_time <= a_time or mid_time >= b_time:
                raise ValueError("Cubic ease-in-out needs at least two frames")
            # Odd frame counts have unequal half durations. Weight the midpoint
            # value by elapsed time so the two cubic halves keep equal velocity.
            fraction = (mid_time - a_time) / (b_time - a_time)
            expanded.append((mid_time, [x + (y - x) * fraction for x, y in zip(a, b, strict=True)]))
            curves.append("ease_in_cubic")
            expanded.append((b_time, b))
            curves.append("ease_out_cubic")
        else:
            expanded.append((b_time, b))
            curves.append(easing)
    spatial = property_name in ("position", "anchor")
    count = 1 if spatial else len(points[0][1])
    keys = [{"time": time, "value": value, "in_speed": [0] * count, "out_speed": [0] * count, "in_type": "linear", "out_type": "linear"} for time, value in expanded]
    for index, easing in enumerate(curves):
        first, last = keys[index:index + 2]
        delta = [b - a for a, b in zip(first["value"], last["value"], strict=True)]
        velocity = [math.sqrt(sum(x * x for x in delta)) / (last["time"] - first["time"])] if spatial else [d / (last["time"] - first["time"]) for d in delta]
        outgoing, incoming = slopes(easing)
        first["out_speed"] = [v * outgoing for v in velocity]
        last["in_speed"] = [v * incoming for v in velocity]
        first["out_type"] = last["in_type"] = "linear" if easing == "linear" else "bezier"
    return {"property": property_name, "keys": keys}
