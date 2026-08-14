from urllib.parse import parse_qs, urlsplit

from browsermcp.tools.powerbi import (
    _filter_reflected,
    _looks_like_query,
    build_filter_url,
    parse_field_refs,
)

# A realistic Power BI semantic-query POST body: three tables aliased in From,
# each contributing one Column/Measure to Select.
FIXTURE_BODY = (
    '{"queries":[{"Query":{"Commands":[{"SemanticQueryDataShapeCommand":'
    '{"Query":{"Version":2,"From":['
    '{"Name":"l","Entity":"Location","Type":0},'
    '{"Name":"s","Entity":"Shrink Actuals","Type":0},'
    '{"Name":"c","Entity":"Calendar","Type":0}],'
    '"Select":['
    '{"Column":{"Expression":{"SourceRef":{"Source":"l"}},"Property":"Division"},'
    '"Name":"Location.Division"},'
    '{"Measure":{"Expression":{"SourceRef":{"Source":"s"}},"Property":"TY Shrink %"},'
    '"Name":"Shrink Actuals.TY Shrink %"},'
    '{"Column":{"Expression":{"SourceRef":{"Source":"c"}},"Property":"Period"},'
    '"Name":"Calendar.Period"}]}}}]}}]}'
)


# --- parse_field_refs -------------------------------------------------------


def test_parse_field_refs_resolves_columns_and_measures():
    fields = parse_field_refs([FIXTURE_BODY])

    assert fields["Division"] == {
        "ref": "Location/Division",
        "entity": "Location",
        "property": "Division",
    }
    assert fields["TY Shrink %"]["ref"] == "Shrink Actuals/TY Shrink %"
    assert fields["TY Shrink %"]["entity"] == "Shrink Actuals"
    assert fields["Period"]["ref"] == "Calendar/Period"


def test_parse_field_refs_skips_invalid_json_body():
    # A non-JSON body must be skipped without raising.
    assert parse_field_refs(["not json {{{"]) == {}


def test_parse_field_refs_empty_list():
    assert parse_field_refs([]) == {}


def test_parse_field_refs_invalid_body_mixed_with_valid():
    fields = parse_field_refs(["<<garbage>>", FIXTURE_BODY])
    assert fields["Division"]["ref"] == "Location/Division"


def test_parse_field_refs_nested_subquery_rebinds_alias():
    # A nested subquery rebinds alias "l" to a different entity within its own
    # scope. The outer "l" -> Location must still resolve; the inner "l" ->
    # Product must resolve to Product, confirming per-scope alias resolution.
    body = (
        '{"Query":{"Version":2,'
        '"From":[{"Name":"l","Entity":"Location","Type":0}],'
        '"Select":[{"Column":{"Expression":{"SourceRef":{"Source":"l"}},'
        '"Property":"Division"},"Name":"Location.Division"}],'
        '"Sub":{"Query":{"From":[{"Name":"l","Entity":"Product","Type":0}],'
        '"Select":[{"Column":{"Expression":{"SourceRef":{"Source":"l"}},'
        '"Property":"Category"},"Name":"Product.Category"}]}}}}'
    )
    fields = parse_field_refs([body])

    assert fields["Division"]["entity"] == "Location"
    assert fields["Category"]["ref"] == "Product/Category"
    assert fields["Category"]["entity"] == "Product"


# --- build_filter_url -------------------------------------------------------


def test_build_filter_url_basic_encoding():
    result = build_filter_url(
        "https://app.powerbi.com/x?experience=power-bi",
        "Location/Division",
        "United",
    )
    assert result.endswith("filter=Location/Division%20eq%20%27United%27")


def test_build_filter_url_preserves_experience_param():
    result = build_filter_url(
        "https://app.powerbi.com/x?experience=power-bi",
        "Location/Division",
        "United",
    )
    assert "experience=power-bi" in result


def test_build_filter_url_replaces_existing_filter():
    url = (
        "https://app.powerbi.com/x?experience=power-bi"
        "&filter=Location/Division%20eq%20%27Old%27"
    )
    result = build_filter_url(url, "Location/Division", "United")
    # Exactly one filter= param survives.
    assert result.count("filter=") == 1
    assert "%27Old%27" not in result
    assert "%27United%27" in result
    assert "experience=power-bi" in result


def test_build_filter_url_escapes_single_quote_in_value():
    result = build_filter_url(
        "https://app.powerbi.com/x?experience=power-bi",
        "Store/Owner",
        "O'Brien",
    )
    # OData escaping doubles the single quote inside the string literal.
    filter_value = parse_qs(urlsplit(result).query)["filter"][0]
    assert filter_value == "Store/Owner eq 'O''Brien'"


# --- _filter_reflected ------------------------------------------------------


def test_filter_reflected_true_when_literal_present():
    assert _filter_reflected(["some where ... 'United' ... clause"], "United") is True


def test_filter_reflected_false_when_absent():
    assert _filter_reflected(["no match here"], "United") is False


def test_filter_reflected_empty_bodies():
    assert _filter_reflected([], "United") is False


# --- _looks_like_query ------------------------------------------------------


def test_looks_like_query_querydata_in_url():
    assert _looks_like_query("https://host/public/reports/querydata", "") is False
    # querydata triggers only when there is a body to inspect.
    assert _looks_like_query("https://host/public/reports/querydata", "x") is True


def test_looks_like_query_semanticquery_in_body():
    assert _looks_like_query("https://host/other", '{"SemanticQuery":1}') is True


def test_looks_like_query_from_and_select_in_body():
    assert _looks_like_query("https://host/other", '{"From":[],"Select":[]}') is True


def test_looks_like_query_empty_body_false():
    assert _looks_like_query("https://host/public/reports/querydata", "") is False
    assert _looks_like_query("https://host/other", "") is False


def test_looks_like_query_unrelated_body_false():
    assert _looks_like_query("https://host/other", '{"foo":"bar"}') is False
