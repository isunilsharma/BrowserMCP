from browsermcp.tools.extraction import (
    _is_flat_simple_schema,
    _is_list_of_records,
    _walk_flat_schema,
)


def test_is_list_of_records_empty_list():
    assert _is_list_of_records([]) is False


def test_is_list_of_records_non_list_input():
    assert _is_list_of_records({"a": 1}) is False
    assert _is_list_of_records("not a list") is False
    assert _is_list_of_records(None) is False


def test_is_list_of_records_list_of_non_dicts():
    assert _is_list_of_records(["a", "b"]) is False
    assert _is_list_of_records([1, 2, 3]) is False


def test_is_list_of_records_first_dict_empty():
    assert _is_list_of_records([{}]) is False


def test_is_list_of_records_non_string_key():
    assert _is_list_of_records([{1: "x"}]) is False


def test_is_list_of_records_nested_dict_value_rejected():
    assert _is_list_of_records([{"k": {"nested": "v"}}]) is False


def test_is_list_of_records_valid_flat_record():
    assert _is_list_of_records([{"name": "str", "value": "str"}]) is True


def test_is_list_of_records_only_first_element_inspected():
    # Implementation only inspects index 0 — later malformed entries don't matter.
    assert _is_list_of_records([{"name": "str"}, {1: "bad"}]) is True


def test_is_flat_simple_schema_empty_dict():
    assert _is_flat_simple_schema({}) is False


def test_is_flat_simple_schema_non_dict():
    assert _is_flat_simple_schema([]) is False
    assert _is_flat_simple_schema("str") is False
    assert _is_flat_simple_schema(None) is False


def test_is_flat_simple_schema_scalar_values():
    assert _is_flat_simple_schema({"name": "str", "age": "int"}) is True
    assert _is_flat_simple_schema({"flag": True, "count": 0}) is True
    assert _is_flat_simple_schema({"typed": str, "also_typed": int}) is True


def test_is_flat_simple_schema_list_of_records_value():
    assert _is_flat_simple_schema({"kpis": [{"name": "str", "value": "str"}]}) is True


def test_is_flat_simple_schema_rejects_nested_dict():
    assert _is_flat_simple_schema({"foo": {"bar": "str"}}) is False


def test_is_flat_simple_schema_rejects_list_of_non_dicts():
    assert _is_flat_simple_schema({"foo": ["a", "b"]}) is False


def test_is_flat_simple_schema_mixed_scalar_and_list_of_records():
    schema = {"name": "str", "items": [{"id": "int", "label": "str"}]}
    assert _is_flat_simple_schema(schema) is True


def test_walk_flat_schema_simple_keys():
    html = (
        "<div>"
        '<span aria-label="username" data-value="alice"></span>'
        '<span aria-label="email" data-value="alice@example.com"></span>'
        "</div>"
    )
    data, sources = _walk_flat_schema(html, {"username": "str", "email": "str"})
    assert data == {"username": "alice", "email": "alice@example.com"}
    assert len(sources) == 2
    assert any("username" in s for s in sources)
    assert any("email" in s for s in sources)


def test_walk_flat_schema_missing_key_omitted_from_data():
    html = '<span aria-label="username" data-value="alice"></span>'
    data, _sources = _walk_flat_schema(html, {"username": "str", "missing": "str"})
    assert data == {"username": "alice"}


def test_walk_flat_schema_empty_html():
    data, sources = _walk_flat_schema("", {"username": "str"})
    assert data == {}
    assert sources == []


def test_walk_flat_schema_list_of_records_kpis():
    html = (
        "<section>"
        '<h2 aria-label="kpis">KPIs</h2>'
        "<div>"
        '<span aria-label="name" data-value="Sales"></span>'
        '<span aria-label="value" data-value="100"></span>'
        "</div>"
        "</section>"
    )
    schema = {"kpis": [{"name": "str", "value": "str"}]}
    data, sources = _walk_flat_schema(html, schema)
    assert "kpis" in data
    assert isinstance(data["kpis"], list)
    assert len(data["kpis"]) >= 1
    first = data["kpis"][0]
    assert first.get("name") == "Sales"
    assert first.get("value") == "100"
    assert any("[kpis#0]" in s for s in sources)


def test_walk_flat_schema_list_of_records_no_anchor_returns_empty():
    # When nothing in the DOM has an accessible name matching the outer key or
    # any field key, no records are emitted and the key is absent from data.
    html = "<div><p>unrelated</p></div>"
    schema = {"kpis": [{"name": "str", "value": "str"}]}
    data, sources = _walk_flat_schema(html, schema)
    assert "kpis" not in data
    assert sources == []
