"""Turn a query result + the model's column mapping into a Chart.js spec.

The chart data is built in Python directly from the real returned rows, so the
numbers shown can never be hallucinated. The LLM only chooses the chart type
and which columns map to labels/values — this module is the safety net that
keeps that choice sane even when the LLM picks a poor column.
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
    """Return a Chart.js-ready dict, or None when a chart would not help."""
    if not viz:
        return None

    rows = result.get("rows") or []
    columns = result.get("columns") or []
    if not rows:
        return None

    chart_type = (viz.get("type") or "none").lower()
    if chart_type not in _CHART_TYPES:
        return None

    label_col = viz.get("label_column")
    if not label_col or label_col not in columns:
        return None

    title = (viz.get("title") or "").strip()
    cap = _PIE_MAX_SLICES if chart_type in ("pie", "doughnut") else max_points

    requested_cols = [c for c in (viz.get("value_columns") or []) if c in columns]
    # Drop identifier/code columns — never valid measures, regardless of what
    # the model picked.
    value_cols = [c for c in requested_cols if not _looks_like_identifier(c)]
    if chart_type in ("pie", "doughnut"):
        value_cols = value_cols[:1]

    # No usable measure column: fall back to counting records per category so
    # the chart still answers something sensible instead of plotting an ID.
    if not value_cols:
        return _build_count_chart(rows, label_col, chart_type, title, cap)

    # If the same label appears more than once, the rows aren't pre-aggregated
    # — sum the measure(s) per label instead of charting raw, duplicate-labeled
    # rows in arbitrary order.
    distinct_labels = {_to_label(r.get(label_col)) for r in rows}
    if len(distinct_labels) < len(rows):
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
