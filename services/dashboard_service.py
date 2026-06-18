"""Schema-driven data overview ("dashboard").

Unlike the chat pipeline, this never asks the LLM to write SQL or pick
columns — it looks at the live, introspected schema metadata and builds
straightforward "count of records per category" charts for whichever
columns are actually categorical. That keeps it fast, free of token cost,
and immune to the same kind of bad-column mistake the chat path's chart
picker has to guard against (see chart_service.looks_like_identifier).
"""
import logging

from .chart_service import looks_like_identifier

log = logging.getLogger("procura.dashboard")

# HANA column types worth grouping by. Numeric/date types are left out of
# this first pass: grouping a continuous measure or a raw timestamp produces
# noise, not insight, without extra bucketing logic.
_CATEGORICAL_TYPES = {
    "VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "SHORTTEXT", "ALPHANUM", "BOOLEAN",
}


class DashboardError(Exception):
    pass


def _select_categorical_columns(columns: list, max_cols: int) -> list:
    picked = []
    for col in columns:
        name = col.get("name") or ""
        dtype = (col.get("type") or "").upper()
        if dtype not in _CATEGORICAL_TYPES:
            continue
        if looks_like_identifier(name):
            continue
        picked.append(name)
        if len(picked) >= max_cols:
            break
    return picked


def _table_total(hana, schema: str, table: str) -> int:
    sql = f'SELECT COUNT(*) AS "TOTAL" FROM "{schema}"."{table}"'
    result = hana.execute_query(sql, max_rows=1)
    rows = result.get("rows") or []
    return int(rows[0]["TOTAL"]) if rows else 0


def _breakdown_chart(hana, schema: str, table: str, column: str, top_n: int):
    sql = (
        f'SELECT "{column}" AS "LABEL", COUNT(*) AS "COUNT" '
        f'FROM "{schema}"."{table}" '
        f'WHERE "{column}" IS NOT NULL '
        f'GROUP BY "{column}" ORDER BY COUNT(*) DESC LIMIT {top_n}'
    )
    result = hana.execute_query(sql, max_rows=top_n)
    rows = result.get("rows") or []
    if not rows:
        return None
    return {
        "type": "bar",
        "title": f"{table} by {column}",
        "labels": [str(r["LABEL"]) for r in rows],
        "datasets": [{"label": "Count", "data": [int(r["COUNT"]) for r in rows]}],
        "truncated_points": False,
    }


def build_table_overview(hana, table_name: str, max_cols: int = 2, top_n: int = 8) -> dict:
    """Overview for one named table: total record count + breakdown charts
    for its most relevant categorical columns."""
    meta = hana.introspect_schema()
    tinfo = meta["tables"].get(table_name)
    if tinfo is None:
        raise DashboardError(f"'{table_name}' is not a known table or view.")

    schema = meta["schema"]
    total = _table_total(hana, schema, table_name)
    charts = []
    for column in _select_categorical_columns(tinfo["columns"], max_cols):
        try:
            chart = _breakdown_chart(hana, schema, table_name, column, top_n)
        except Exception:  # noqa: BLE001 - skip a bad column, don't fail the page
            log.exception("Breakdown failed for %s.%s", table_name, column)
            continue
        if chart:
            charts.append(chart)

    return {"table": table_name, "total_records": total, "charts": charts}


def build_dashboard(hana, max_tables: int = 6, max_cols_per_table: int = 2,
                     top_n: int = 8) -> dict:
    """A full, generic overview: one section per table/view that has at
    least one categorical column and at least one record."""
    meta = hana.introspect_schema()
    schema = meta["schema"]
    sections = []

    for table_name, tinfo in meta["tables"].items():
        if len(sections) >= max_tables:
            break
        categorical_cols = _select_categorical_columns(
            tinfo["columns"], max_cols_per_table
        )
        if not categorical_cols:
            continue
        try:
            total = _table_total(hana, schema, table_name)
        except Exception:  # noqa: BLE001 - some objects may not be selectable
            log.info("Skipping %s in dashboard: count failed", table_name)
            continue
        if not total:
            continue

        charts = []
        for column in categorical_cols:
            try:
                chart = _breakdown_chart(hana, schema, table_name, column, top_n)
            except Exception:  # noqa: BLE001
                log.info("Skipping %s.%s in dashboard", table_name, column)
                continue
            if chart:
                charts.append(chart)

        if charts:
            sections.append(
                {"table": table_name, "total_records": total, "charts": charts}
            )

    return {"schema": schema, "sections": sections}
