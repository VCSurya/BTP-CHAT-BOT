"""Turn a query result + the model's column mapping into a Chart.js spec.

The chart data is built in Python directly from the real returned rows, so the
numbers shown can never be hallucinated. The LLM's column/type choices are
just a hint — this module is the safety net that fills in (or overrides) that
choice whenever it is missing, stale, or unusable, by inferring directly from
the live data shape. That makes it work for ANY result set (one metric, many
metrics, pre-aggregated or not, with or without a model-provided mapping at
all), not just the shapes the model happens to get right.
"""
from collections import OrderedDict

_CHART_TYPES = {"bar", "line", "pie", "doughnut"}

# Columns named like these are identifiers/codes, not measures: a material ID,
# PO number, vendor ID, etc. is unique per record and meaningless to sum or
# plot on a value axis, even though it happens to look numeric. They are only
# ever safe to use as labels, never as chart values.
_ID_SUFFIXES = ("ID", "CODE", "NUMBER", "GUID", "UUID")

# Pie/doughnut charts stop being readable well before the generic point cap.
_PIE_MAX_SLICES = 8

# A label axis with more distinct categories than this is too dense to read
# as a chart at all (a wide table is the better presentation).
_MAX_CHARTABLE_CATEGORIES = 200


def looks_like_identifier(col_name: str) -> bool:
    """True for columns that are identifiers/codes rather than measures.

    Shared with dashboard_service so both the chat path and the schema-driven
    dashboard agree on what counts as a real, chartable value column.
    """
    name = (col_name or "").upper().replace("_", "").replace(" ", "")
    return any(name.endswith(suffix) for suffix in _ID_SUFFIXES)


# Backward-compatible alias for the old private name.
_looks_like_identifier = looks_like_identifier


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _to_label(value):
    if value is None:
        return ""
    return str(value)


def _column_is_numeric(rows, col, sample_size=50) -> bool:
    """A column counts as numeric only if every non-null sampled value parses
    as a number — a column that mixes text and numbers is not a measure."""
    seen = 0
    for row in rows[:sample_size]:
        value = row.get(col)
        if value is None or value == "":
            continue
        seen += 1
        if _to_number(value) is None:
            return False
    return seen > 0


def infer_columns(columns: list, rows: list):
    """Best-effort (label_column, value_columns) guess from the real data,
    used whenever the model's mapping is missing, invalid, or stale for the
    data actually returned. Works for any column layout:
      - one category + one measure (the common case)
      - one category + several measures (multi-series bar/line)
      - no real measure at all (falls back to None so the caller can count
        records per category instead)
      - no usable category either (returns the first column as a last resort)
    """
    if not columns or not rows:
        return None, []

    numeric_cols = [c for c in columns if _column_is_numeric(rows, c)]
    text_cols = [c for c in columns if c not in numeric_cols]

    # Prefer a non-identifier text column as the label (e.g. VENDORNAME over
    # VENDORCODE). Fall back to any text column, then any column at all.
    label_candidates = (
        [c for c in text_cols if not looks_like_identifier(c)]
        or text_cols
        or [c for c in numeric_cols if not looks_like_identifier(c)]
        or columns
    )
    label_col = label_candidates[0]

    value_cols = [
        c for c in numeric_cols
        if c != label_col and not looks_like_identifier(c)
    ]
    return label_col, value_cols


def _is_chartable_shape(label_col, rows, distinct_count) -> bool:
    """True when the data shape is genuinely worth visualising: a real
    category axis with more than one row and a sane number of categories.
    A single-row record lookup (e.g. 'show me PO 123's details') or an
    overly dense category axis should stay a table instead."""
    if not label_col or len(rows) < 2:
        return False
    return 1 < distinct_count <= _MAX_CHARTABLE_CATEGORIES


def _default_chart_type(label_col, rows, distinct_count) -> str:
    """Pick a sensible default chart type purely from the data shape, for
    when the model didn't choose one (or chose "none" on data that is
    actually chartable)."""
    sample = [r.get(label_col) for r in rows if r.get(label_col) is not None]
    if sample and all(_to_number(v) is None and _looks_like_date(v) for v in sample[:10]):
        return "line"
    if distinct_count <= 6:
        return "doughnut"
    return "bar"


def _looks_like_date(value) -> bool:
    text = str(value)
    if len(text) < 7:
        return False
    return text[:4].isdigit() and ("-" in text or "/" in text)


def _build_count_chart(rows, label_col, chart_type, title, cap):
    """No usable measure column: chart how many records fall in each category."""
    counts = OrderedDict()
    for row in rows:
        label = _to_label(row.get(label_col))
        counts[label] = counts.get(label, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    truncated = len(ranked) > cap
    ranked = ranked[:cap]

    return {
        "type": chart_type,
        "title": title or f"Count by {label_col}",
        "labels": [label for label, _ in ranked],
        "datasets": [{"label": "Count", "data": [count for _, count in ranked]}],
        "truncated_points": truncated,
    }


def _build_aggregated_chart(rows, label_col, value_cols, chart_type, title, cap):
    """Rows aren't pre-aggregated (a label repeats) — sum each measure per label
    instead of charting raw per-row values under duplicate category labels."""
    totals = OrderedDict()
    for row in rows:
        label = _to_label(row.get(label_col))
        bucket = totals.setdefault(label, [0.0] * len(value_cols))
        for i, col in enumerate(value_cols):
            num = _to_number(row.get(col))
            if num is not None:
                bucket[i] += num

    ranked = sorted(totals.items(), key=lambda kv: kv[1][0], reverse=True)
    truncated = len(ranked) > cap
    ranked = ranked[:cap]

    datasets = []
    for i, col in enumerate(value_cols):
        series = [vals[i] for _, vals in ranked]
        if all(v == 0 for v in series):
            continue
        datasets.append({"label": col, "data": series})

    if not datasets:
        return None

    return {
        "type": chart_type,
        "title": title,
        "labels": [label for label, _ in ranked],
        "datasets": datasets,
        "truncated_points": truncated,
    }


def build_chart(result: dict, viz: dict, max_points: int = 30):
    """Return a Chart.js-ready dict, or None when a chart genuinely would not
    help (a single-record lookup, no category axis, too many categories).

    The model's viz mapping is only a hint: any missing or invalid piece
    (label column, value columns, even the chart type itself) is filled in
    by inferring directly from the real rows, so this works for any data
    shape the SQL happens to return — single metric, multiple metrics,
    pre-aggregated or not, or no model mapping supplied at all (e.g. when
    re-charting a previous answer that was originally shown as a table).
    """
    rows = result.get("rows") or []
    columns = result.get("columns") or []
    if not rows or not columns:
        return None

    viz = viz or {}
    title = (viz.get("title") or "").strip()

    label_col = viz.get("label_column")
    if not label_col or label_col not in columns:
        label_col = None

    requested_cols = [c for c in (viz.get("value_columns") or []) if c in columns]
    # Drop identifier/code columns — never valid measures, regardless of what
    # the model picked.
    value_cols = [c for c in requested_cols if not _looks_like_identifier(c)]

    # Fill in whatever the model's mapping didn't give us by inferring from
    # the actual data, so a missing/stale mapping never blocks a chart that
    # the data clearly supports.
    if label_col is None or not value_cols:
        inferred_label, inferred_values = infer_columns(columns, rows)
        label_col = label_col or inferred_label
        if not value_cols:
            value_cols = inferred_values

    if not label_col:
        return None

    distinct_count = len({_to_label(r.get(label_col)) for r in rows})

    chart_type = (viz.get("type") or "").lower()
    if chart_type not in _CHART_TYPES:
        # The model didn't choose a real type (or said "none"). Only force a
        # chart when the data shape genuinely supports one.
        if not _is_chartable_shape(label_col, rows, distinct_count):
            return None
        chart_type = _default_chart_type(label_col, rows, distinct_count)

    cap = _PIE_MAX_SLICES if chart_type in ("pie", "doughnut") else max_points
    if chart_type in ("pie", "doughnut"):
        value_cols = value_cols[:1]

    # No usable measure column: fall back to counting records per category so
    # the chart still answers something sensible instead of plotting an ID.
    if not value_cols:
        if distinct_count <= 1:
            return None
        return _build_count_chart(rows, label_col, chart_type, title, cap)

    # If the same label appears more than once, the rows aren't pre-aggregated
    # — sum the measure(s) per label instead of charting raw, duplicate-labeled
    # rows in arbitrary order.
    if distinct_count < len(rows):
        return _build_aggregated_chart(
            rows, label_col, value_cols, chart_type, title, cap
        )

    sample = rows[:cap]
    labels = [_to_label(r.get(label_col)) for r in sample]

    datasets = []
    for col in value_cols:
        series = [_to_number(r.get(col)) for r in sample]
        if all(v is None for v in series):
            continue
        datasets.append({"label": col, "data": series})

    if not datasets:
        return None

    return {
        "type": chart_type,
        "title": title,
        "labels": labels,
        "datasets": datasets,
        "truncated_points": len(rows) > len(sample),
    }
