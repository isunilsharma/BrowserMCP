from typing import Any, Literal

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class Element(BaseModel):
    ref: str
    role: str
    name: str
    visible: bool = True
    bounding_box: BBox | None = None


class AttachResult(BaseModel):
    profile_name: str
    context_id: str
    pages_open: int


class WindowRef(BaseModel):
    window_id: str


class NavigateResult(BaseModel):
    title: str
    url: str


class ClickResult(BaseModel):
    description: str
    ok: bool = True
    notes: str | None = None


class TypeResult(BaseModel):
    field: str
    chars_typed: int
    ok: bool = True
    notes: str | None = None


class PageReadResult(BaseModel):
    title: str
    url: str
    text: str
    elements: list[Element] = Field(default_factory=list)
    accessibility_tree: dict = Field(default_factory=dict)
    links: list[dict] = Field(default_factory=list)


class ScreenshotResult(BaseModel):
    path: str


class ExtractResult(BaseModel):
    data: dict
    source_elements: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class ScrollResult(BaseModel):
    direction: str
    pixels: int


class EvaluateResult(BaseModel):
    ok: bool = True
    result: Any = None
    notes: str | None = None


class PowerBIField(BaseModel):
    ref: str
    entity: str
    property: str


class PowerBIFieldsResult(BaseModel):
    url: str
    captured: int
    fields: dict[str, PowerBIField] = Field(default_factory=dict)
    notes: str | None = None


class PowerBISetFilterResult(BaseModel):
    ref: str
    value: str
    url: str
    applied: bool
    captured: int = 0
    notes: str | None = None
