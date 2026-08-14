import pytest

from browsermcp.models import (
    AttachResult,
    BBox,
    ClickResult,
    Element,
    ExtractResult,
    NavigateResult,
    PageReadResult,
    ScreenshotResult,
    ScrollResult,
    TypeResult,
    WindowRef,
)


def test_bbox_instantiates():
    bbox = BBox(x=1, y=2, w=100, h=50)
    assert bbox.x == 1
    assert bbox.y == 2
    assert bbox.w == 100
    assert bbox.h == 50


def test_element_defaults():
    el = Element(ref="r1", role="button", name="Submit")
    assert el.visible is True
    assert el.bounding_box is None


def test_element_with_bbox():
    el = Element(
        ref="r2",
        role="link",
        name="Home",
        visible=False,
        bounding_box=BBox(x=0, y=0, w=10, h=10),
    )
    assert el.visible is False
    assert el.bounding_box.w == 10


def test_attach_result():
    a = AttachResult(profile_name="Default", context_id="ctx-1", pages_open=3)
    assert a.pages_open == 3


def test_window_ref():
    w = WindowRef(window_id="w-1")
    assert w.window_id == "w-1"


def test_navigate_result():
    n = NavigateResult(title="Home", url="https://example.com")
    assert n.title == "Home"
    assert n.url == "https://example.com"


def test_click_result_defaults():
    c = ClickResult(description="clicked submit")
    assert c.ok is True
    assert c.notes is None


def test_click_result_with_notes():
    c = ClickResult(description="clicked submit", ok=False, notes="not found")
    assert c.ok is False
    assert c.notes == "not found"


def test_type_result_defaults():
    t = TypeResult(field="email", chars_typed=12)
    assert t.ok is True


def test_page_read_result_defaults():
    p = PageReadResult(title="t", url="https://x", text="body")
    assert p.elements == []
    assert p.accessibility_tree == {}


def test_page_read_result_with_elements():
    p = PageReadResult(
        title="t",
        url="https://x",
        text="body",
        elements=[Element(ref="r1", role="button", name="Go")],
        accessibility_tree={"role": "WebArea"},
    )
    assert len(p.elements) == 1
    assert p.accessibility_tree["role"] == "WebArea"


def test_screenshot_result():
    s = ScreenshotResult(path="/tmp/x.png")
    assert s.path == "/tmp/x.png"


def test_extract_result_defaults():
    e = ExtractResult(data={"k": "v"})
    assert e.source_elements == []
    assert e.confidence == "medium"


def test_extract_result_confidence_values():
    for c in ("high", "medium", "low"):
        e = ExtractResult(data={}, confidence=c)
        assert e.confidence == c


def test_extract_result_invalid_confidence_rejected():
    with pytest.raises(Exception):
        ExtractResult(data={}, confidence="unknown")


def test_scroll_result():
    s = ScrollResult(direction="down", pixels=500)
    assert s.direction == "down"
    assert s.pixels == 500


def test_navigate_result_missing_field_rejected():
    with pytest.raises(Exception):
        NavigateResult(title="only title")
