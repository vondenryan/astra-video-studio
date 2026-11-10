from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComponentStatus(BaseModel):
    available: bool = False
    path: str | None = None
    version: str | None = None
    error: str | None = None


class WorkspaceStatus(BaseModel):
    path: str
    writable: bool
    error: str | None = None


class StudioStatus(BaseModel):
    operation_id: str
    timestamp: str
    status: Literal["ok", "degraded"]
    platform: str
    windows_supported: bool
    python_version: str
    after_effects: ComponentStatus
    ffmpeg: ComponentStatus
    ffprobe: ComponentStatus
    workspace: WorkspaceStatus
    bridge_status: Literal["not_validated", "acknowledged"] = "not_validated"
    bridge_runtime: dict = Field(default_factory=dict)
    mcp_runtime: dict = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(default="Astra Demo", min_length=1, max_length=120)
    title: str = Field(default="ASTRA VIDEO STUDIO", min_length=1, max_length=500)
    width: int = Field(default=1920, ge=64, le=7680)
    height: int = Field(default=1080, ge=64, le=4320)
    fps: float = Field(default=30, ge=1, le=120)
    duration: float = Field(default=5, ge=0.1, le=300)
    font_size: float = Field(default=90, ge=8, le=500)

    @field_validator("name", "title")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("Text must be nonempty and contain no unsupported control characters")
        return value


class OperationResult(BaseModel):
    operation_id: str
    status: Literal["succeeded", "failed", "blocked", "timeout", "busy", "queued", "running", "cancelled"]
    project_id: str | None = None
    project_path: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    error: str | None = None


class JobStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    operation_id: str
    action: str
    status: str
    events: list[dict]
    result: OperationResult | None = None


class ProjectOpenCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_path: str = Field(min_length=1, max_length=32767)
