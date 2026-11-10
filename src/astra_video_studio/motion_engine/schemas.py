from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Easing = Literal["linear", "ease_in_cubic", "ease_out_cubic", "ease_in_out_cubic"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Target(StrictModel):
    project_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    composition_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    layer_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class TransformValues(StrictModel):
    position: tuple[float, float] | None = None
    anchor: tuple[float, float] | None = None
    scale: tuple[float, float] | None = None
    rotation: float | None = Field(default=None, ge=-36000, le=36000)
    opacity: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def limits(self):
        if not any(v is not None for v in self.model_dump().values()):
            raise ValueError("Supply at least one transform")
        for vector in (self.position, self.anchor):
            if vector and any(abs(v) > 100000 for v in vector):
                raise ValueError("Coordinates exceed +/-100000 pixels")
        if self.scale and any(v <= 0 or v > 1000 for v in self.scale):
            raise ValueError("Scale must be greater than 0 and at most 1000 percent")
        return self


class TransformRequest(Target):
    values: TransformValues


class SlideParams(StrictModel):
    direction: Literal["left", "right", "up", "down"] = "left"
    distance_px: float | None = Field(default=None, gt=0, le=10000)
    distance_ratio: float = Field(default=0.24, gt=0, le=2)
    easing: Easing = "ease_out_cubic"
    overshoot: float = Field(default=0.06, ge=0, le=0.25)
    motion_blur: bool = True


class ScalePopParams(StrictModel):
    initial_scale: float = Field(default=70, gt=0, le=1000)
    final_scale: float = Field(default=100, gt=0, le=800)
    overshoot: float = Field(default=0.08, ge=0, le=0.25)
    easing: Easing = "ease_out_cubic"
    motion_blur: bool = True


class FadeParams(StrictModel):
    fade_in: float = Field(default=0.6, gt=0, le=60)
    fade_out: float = Field(default=0.8, gt=0, le=60)
    easing: Easing = "ease_in_out_cubic"
    motion_blur: bool = False


class ZoomParams(StrictModel):
    initial_scale: float = Field(default=100, gt=0, le=1000)
    final_scale: float = Field(default=110, gt=0, le=1000)
    easing: Easing = "ease_in_out_cubic"
    motion_blur: bool = True


class RevealParams(StrictModel):
    direction: Literal["left", "right", "up", "down"] = "left"
    padding_px: float = Field(default=8, ge=0, le=100)
    easing: Easing = "ease_in_out_cubic"
    motion_blur: bool = False


class ShakeParams(StrictModel):
    amplitude_px: float = Field(default=6, gt=0, le=100)
    frequency_hz: float = Field(default=4, ge=0.5, le=12)
    decay: float = Field(default=3, ge=0, le=10)
    seed: int = Field(default=0, ge=0, le=2147483647)
    motion_blur: bool = True


class ParallaxParams(StrictModel):
    depth: float = Field(default=0.5, gt=0, le=2)
    displacement: tuple[float, float] = (0.04, 0)
    easing: Easing = "ease_in_out_cubic"
    motion_blur: bool = True

    @model_validator(mode="after")
    def displacement_bounds(self):
        if any(abs(v) > 1 for v in self.displacement):
            raise ValueError("Parallax displacement is limited to +/-1 composition size")
        return self


class AnticipateParams(SlideParams):
    anticipation_ratio: float = Field(default=0.08, ge=0, le=0.25)


PARAMS = {"slide_in": SlideParams, "scale_pop": ScalePopParams, "fade_in_out": FadeParams, "smooth_zoom": ZoomParams, "text_reveal": RevealParams, "shake": ShakeParams, "parallax_2d": ParallaxParams, "anticipate_settle": AnticipateParams}


class MotionRequest(Target):
    skill: Literal["slide_in", "scale_pop", "fade_in_out", "smooth_zoom", "text_reveal", "shake", "parallax_2d", "anticipate_settle"]
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=2, gt=0, le=300)
    params: SlideParams | ScalePopParams | FadeParams | ZoomParams | RevealParams | ShakeParams | ParallaxParams | AnticipateParams = Field(default_factory=SlideParams)

    @model_validator(mode="before")
    @classmethod
    def select_params(cls, data):
        if isinstance(data, dict) and data.get("skill") in PARAMS:
            data = dict(data)
            raw = data.get("params", {})
            if isinstance(raw, BaseModel):
                raw = raw.model_dump()
            data["params"] = PARAMS[data["skill"]].model_validate(raw)
        return data
