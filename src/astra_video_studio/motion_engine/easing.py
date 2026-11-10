"""Cubic easing functions and AE temporal tangent endpoint slopes."""


def evaluate(name: str, t: float) -> float:
    if not 0 <= t <= 1:
        raise ValueError("Easing time must be between 0 and 1")
    if name == "linear":
        return t
    if name == "ease_in_cubic":
        return t ** 3
    if name == "ease_out_cubic":
        return 1 - (1 - t) ** 3
    if name == "ease_in_out_cubic":
        return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
    raise ValueError("Unknown easing")


def slopes(name: str) -> tuple[float, float]:
    # ease_in_out is split into its two cubic halves by the timeline compiler.
    return {"linear": (1, 1), "ease_in_cubic": (0, 3), "ease_out_cubic": (3, 0)}[name]
