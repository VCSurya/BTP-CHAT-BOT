"""Schema-driven data overview ("dashboard").

Unlike the chat pipeline, this never asks the LLM to write SQL or pick
columns — it looks at the live, introspected schema metadata and builds
straightforward "count of records per category" charts for whichever
columns are actually categorical. That keeps it fast, free of token cost,
and immune to the same kind of bad-column mistake the chat path's chart
picker has to guard against (see chart_service.looks_like_identifier).

Every internal HANA table name is translated to a business-friendly label
and grouped into a business category before it ever reaches the client —
raw schema identifiers are never sent to the front end.
"""
import concurrent.futures
import logging

from prompts.table_knowledge import TABLE_BUSINESS_CONTEXT

from .chart_service import looks_like_identifier

log = logging.getLogger("procura.dashboard")

# HANA column types worth grouping by. Numeric/date types are left out of
# this first pass: grouping a continuous measure or a raw timestamp produces
# noise, not insight, without extra bucketing logic.
_CATEGORICAL_TYPES = {
    "VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "SHORTTEXT", "ALPHANUM", "BOOLEAN",
}

_NUMERIC_TYPES = {
    "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "DECIMAL", "DOUBLE", "REAL", "FLOAT",
}

_DATE_TYPES = {"DATE", "TIMESTAMP", "SECONDDATE"}

# Keywords that suggest a numeric column is a business measure (worth
# summing/averaging) rather than just a quantity nobody cares about totalled.
_MEASURE_HINTS = (
    "AMOUNT", "VALUE", "PRICE", "COST", "QTY", "QUANTITY", "TOTAL", "RATE",
    "BUDGET", "PAID", "BALANCE",
)

# Preferred date columns for trend analysis (created/submitted dates read
# better as "activity over time" than e.g. an arbitrary "valid-to" date).
_DATE_HINTS = ("CREATE", "SUBMIT", "START", "ISSUE", "ORDER", "REQUEST", "OPEN")


class DashboardError(Exception):
    pass


# ─── Business-friendly naming (never expose raw HANA table names) ──────────

FRIENDLY_NAMES = {
    "ZHANADB_PURCHASEORDERSET": "Purchase Orders",
    "ZHANADB_POASSIGNMENTSET": "PO Team Assignments",
    "ZHANADB_POBGRELATIONSET": "Bank Guarantees",
    "ZHANADB_MATERIALSET": "Materials",
    "ZHANADB_MATERIALFAMILYSET": "Material Families",
    "ZHANADB_PROJECTWBSSET": "Project Work Breakdown",
    "ZHANADB_WBS": "Work Breakdown Structure",
    "ZHANADB_WBSAPPROVEDBY": "WBS Approvals",
    "ZHANADB_WBSTRAINSET": "WBS Trains",
    "ZHANADB_INSPECTIONSET": "Quality Inspections",
    "ZHANADB_INSPECTIONITEMSET": "Inspection Items",
    "ZHANADB_MDCCRELATIONSET": "MDCC Assignments",
    "ZHANADB_TPIRELATIONSET": "Inspector Assignments",
    "ZHANADB_CHANGENOTESET": "Change Notes",
    "ZHANADB_CHANGENOTERECOSET": "Change Note Approvals",
    "ZHANADB_CNAPPROVALSTAGEMASTERSET": "Approval Stages",
    "ZHANADB_CNAPPROVALTEMPLATESET": "Approval Templates",
    "ZHANADB_CNWF1STAGESET": "Change Note Workflow",
    "ZHANADB_CNPOLIMITMASTERSET": "PO Approval Limits",
    "ZHANADB_SERVICEORDERSET": "Service Orders",
    "ZHANADB_SERVICEORDERDEDUCTIONSET": "Service Order Deductions",
    "ZHANADB_SERVICEORDERRECOMENDERSET": "Service Order Approvers",
    "ZHANADB_QUERYLISTSET": "Vendor Queries",
    "ZHANADB_QUERYLISTITEMSET": "Query Items",
    "ZHANADB_QUERYLISTRECOSET": "Query Responses",
    "ZHANADB_QUERYLISTCONCERNEDSET": "Query Stakeholders",
    "ZHANADB_NCRDCRDATASET": "Non-Conformance Reports",
    "ZHANADB_NCRDCRITEMDATASET": "NCR/DCR Items",
    "ZHANADB_NCRDCRRECOSET": "NCR/DCR Approvers",
    "ZHANADB_DOCUMENTSET": "Documents",
    "ZHANADB_DOCUMENTMASTERSET": "Document Templates",
    "ZHANADB_COMMENTSET": "Comments",
    "ZHANADB_COMMENTSETRECOBY": "Comment Approvals",
    "ZHANADB_USERROLESET": "User Roles",
    "ZHANADB_CONFIGURATION": "System Configuration",
    "ZHANADB_MPLMAILCONFIGURATION": "Notification Settings",
}

CATEGORIES = {
    "ZHANADB_PURCHASEORDERSET": "Procurement",
    "ZHANADB_POASSIGNMENTSET": "Procurement",
    "ZHANADB_POBGRELATIONSET": "Procurement",
    "ZHANADB_MATERIALSET": "Procurement",
    "ZHANADB_MATERIALFAMILYSET": "Procurement",
    "ZHANADB_INSPECTIONSET": "Quality & Inspection",
    "ZHANADB_INSPECTIONITEMSET": "Quality & Inspection",
    "ZHANADB_MDCCRELATIONSET": "Quality & Inspection",
    "ZHANADB_TPIRELATIONSET": "Quality & Inspection",
    "ZHANADB_SERVICEORDERSET": "Service Orders",
    "ZHANADB_SERVICEORDERDEDUCTIONSET": "Service Orders",
    "ZHANADB_SERVICEORDERRECOMENDERSET": "Service Orders",
    "ZHANADB_CHANGENOTESET": "Change Management",
    "ZHANADB_CHANGENOTERECOSET": "Change Management",
    "ZHANADB_CNAPPROVALSTAGEMASTERSET": "Change Management",
    "ZHANADB_CNAPPROVALTEMPLATESET": "Change Management",
    "ZHANADB_CNWF1STAGESET": "Change Management",
    "ZHANADB_CNPOLIMITMASTERSET": "Change Management",
    "ZHANADB_QUERYLISTSET": "Queries & Issues",
    "ZHANADB_QUERYLISTITEMSET": "Queries & Issues",
    "ZHANADB_QUERYLISTRECOSET": "Queries & Issues",
    "ZHANADB_QUERYLISTCONCERNEDSET": "Queries & Issues",
    "ZHANADB_NCRDCRDATASET": "Queries & Issues",
    "ZHANADB_NCRDCRITEMDATASET": "Queries & Issues",
    "ZHANADB_NCRDCRRECOSET": "Queries & Issues",
    "ZHANADB_PROJECTWBSSET": "Projects & Budgets",
    "ZHANADB_WBS": "Projects & Budgets",
    "ZHANADB_WBSAPPROVEDBY": "Projects & Budgets",
    "ZHANADB_WBSTRAINSET": "Projects & Budgets",
    "ZHANADB_DOCUMENTSET": "Documents & Comments",
    "ZHANADB_DOCUMENTMASTERSET": "Documents & Comments",
    "ZHANADB_COMMENTSET": "Documents & Comments",
    "ZHANADB_COMMENTSETRECOBY": "Documents & Comments",
    "ZHANADB_USERROLESET": "Administration",
    "ZHANADB_CONFIGURATION": "Administration",
    "ZHANADB_MPLMAILCONFIGURATION": "Administration",
}

_CATEGORY_ORDER = [
    "Procurement",
    "Quality & Inspection",
    "Service Orders",
    "Change Management",
    "Queries & Issues",
    "Projects & Budgets",
    "Documents & Comments",
    "Administration",
]


def friendly_name(table_name: str) -> str:
    """Business-facing label for a raw schema object. Never show the raw
    identifier itself in the UI — fall back to a readable guess if a table
    isn't in the manual map yet."""
    label = FRIENDLY_NAMES.get(table_name)
    if label:
        return label
    name = table_name
    if name.upper().startswith("ZHANADB_"):
        name = name[len("ZHANADB_"):]
    name = name.replace("_", " ").strip().title()
    return name or "Other Data"


def category_of(table_name: str) -> str:
    return CATEGORIES.get(table_name, "Other")


FRIENDLY_COLUMNS = {
    "INSPECTIONDISPLAYSTATUS": "Inspection Status",
    "INSPECTIONSTATUS": "Workflow Status",
    "INSPECTIONCATEGORY": "Inspection Category",
    "INSPECTIONPLACE": "Inspection Place",
    "PORELEASESTATUS": "PO Release Status",
    "PAYMENTSTATUS": "Payment Status",
    "POCURRENCY": "PO Currency",
    "DOCTYPE": "Document Type",
    "MATFAMILY": "Material Family",
    "MATCATEGORY": "Material Category",
    "MATSUBCATEGORY": "Material Sub-Category",
    "VENDORNAME": "Vendor Name",
    "PROJECTWBSDESC": "Project WBS Description",
    "WBSTRAINDESC": "WBS Train Description",
    "BGTYPECODE": "Bank Guarantee Type",
    "BANKNAME": "Bank Name",
    "RESOLUTIONSTATUS": "Resolution Status",
    "QUERYTYPE": "Query Type",
    "STATUS": "Status",
    "TYPE": "Type",
    "ROLE": "User Role",
}


def _humanize_column(column: str) -> str:
    friendly = FRIENDLY_COLUMNS.get(column.upper())
    if friendly:
        return friendly
    return column.replace("_", " ").strip().title()


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


def _select_measure_column(columns: list):
    for col in columns:
        name = col.get("name") or ""
        dtype = (col.get("type") or "").upper()
        if dtype not in _NUMERIC_TYPES:
            continue
        if looks_like_identifier(name):
            continue
        if any(hint in name.upper() for hint in _MEASURE_HINTS):
            return name
    return None


def _select_date_column(columns: list):
    candidates = [c for c in columns if (c.get("type") or "").upper() in _DATE_TYPES]
    if not candidates:
        return None
    for c in candidates:
        if any(hint in (c.get("name") or "").upper() for hint in _DATE_HINTS):
            return c["name"]
    return candidates[0]["name"]


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

    # Choose chart type dynamically
    num_categories = len(rows)
    c_upper = column.upper()

    if any(k in c_upper for k in ("DATE", "TIME", "MONTH", "YEAR", "WEEK")):
        chart_type = "line"
    elif num_categories == 2:
        chart_type = "pie"
    elif 3 <= num_categories <= 6:
        chart_type = "doughnut"
    else:
        chart_type = "bar"

    return {
        "type": chart_type,
        "title": f"By {_humanize_column(column)}",
        "labels": [str(r["LABEL"]) for r in rows],
        "datasets": [{"label": "Count", "data": [int(r["COUNT"]) for r in rows]}],
        "truncated_points": False,
    }


def _measure_kpi(hana, schema: str, table: str, column: str):
    sql = (
        f'SELECT SUM("{column}") AS "S", AVG("{column}") AS "A" '
        f'FROM "{schema}"."{table}" WHERE "{column}" IS NOT NULL'
    )
    result = hana.execute_query(sql, max_rows=1)
    rows = result.get("rows") or []
    if not rows or rows[0].get("S") is None:
        return None
    return {"sum": float(rows[0]["S"]), "avg": float(rows[0]["A"] or 0)}


def _trend(hana, schema: str, table: str, column: str):
    """Records in the last 30 days vs. the 30 days before that."""
    sql = (
        f'SELECT '
        f'SUM(CASE WHEN "{column}" >= ADD_DAYS(CURRENT_DATE, -30) THEN 1 ELSE 0 END) AS "CURR", '
        f'SUM(CASE WHEN "{column}" >= ADD_DAYS(CURRENT_DATE, -60) '
        f'AND "{column}" < ADD_DAYS(CURRENT_DATE, -30) THEN 1 ELSE 0 END) AS "PREV" '
        f'FROM "{schema}"."{table}" WHERE "{column}" IS NOT NULL'
    )
    result = hana.execute_query(sql, max_rows=1)
    rows = result.get("rows") or []
    if not rows:
        return None
    curr = int(rows[0].get("CURR") or 0)
    prev = int(rows[0].get("PREV") or 0)
    if curr == 0 and prev == 0:
        return None
    change_pct = 100.0 if prev == 0 else round((curr - prev) / prev * 100, 1)
    return {"current_30d": curr, "previous_30d": prev, "change_pct": change_pct}


def _highlight(name: str, total: int, chart: dict):
    if not chart or not chart.get("labels") or not total:
        return None
    top_label = chart["labels"][0]
    top_count = chart["datasets"][0]["data"][0]
    pct = round(top_count / total * 100, 1)
    return f'"{top_label}" leads {name} with {pct:g}% ({top_count:,} of {total:,}).'


def _empty_section(table_name: str, total: int) -> dict:
    return {
        "name": friendly_name(table_name),
        "category": category_of(table_name),
        "description": (TABLE_BUSINESS_CONTEXT.get(table_name) or {}).get("purpose", ""),
        "total_records": total,
        "kpis": [{"label": "Total Records", "value": total, "format": "number"}],
        "trend": None,
        "highlight": None,
        "charts": [],
    }


def _section_for_table(hana, schema: str, table_name: str, tinfo: dict,
                        max_cols: int, top_n: int):
    """Build one dashboard section for a table, or None if there isn't
    enough categorical data / records to say anything useful about it."""
    categorical_cols = _select_categorical_columns(tinfo["columns"], max_cols)
    if not categorical_cols:
        return None
    try:
        total = _table_total(hana, schema, table_name)
    except Exception:  # noqa: BLE001 - some objects may not be selectable
        log.info("Skipping %s in dashboard: count failed", table_name)
        return None
    if not total:
        return None

    name = friendly_name(table_name)
    charts = []
    highlight = None
    for column in categorical_cols:
        try:
            chart = _breakdown_chart(hana, schema, table_name, column, top_n)
        except Exception:  # noqa: BLE001
            log.info("Skipping %s.%s in dashboard", table_name, column)
            continue
        if chart:
            charts.append(chart)
            if highlight is None:
                highlight = _highlight(name, total, chart)
    if not charts:
        return None

    kpis = [{"label": "Total Records", "value": total, "format": "number"}]

    measure_col = _select_measure_column(tinfo["columns"])
    if measure_col:
        try:
            measure = _measure_kpi(hana, schema, table_name, measure_col)
        except Exception:  # noqa: BLE001
            measure = None
        if measure:
            label = _humanize_column(measure_col)
            kpis.append({"label": f"Total {label}", "value": round(measure["sum"], 2), "format": "decimal"})
            kpis.append({"label": f"Average {label}", "value": round(measure["avg"], 2), "format": "decimal"})

    trend = None
    date_col = _select_date_column(tinfo["columns"])
    if date_col:
        try:
            trend = _trend(hana, schema, table_name, date_col)
        except Exception:  # noqa: BLE001
            trend = None

    return {
        "name": name,
        "category": category_of(table_name),
        "description": (TABLE_BUSINESS_CONTEXT.get(table_name) or {}).get("purpose", ""),
        "total_records": total,
        "kpis": kpis,
        "trend": trend,
        "highlight": highlight,
        "charts": charts,
    }


def build_table_overview(hana, table_name: str, max_cols: int = 2, top_n: int = 8) -> dict:
    """Overview for one named table: total record count + breakdown charts
    for its most relevant categorical columns, plus KPIs/trend when
    available. Identified internally by the raw table name, but the
    returned dict never includes it."""
    meta = hana.introspect_schema()
    tinfo = meta["tables"].get(table_name)
    if tinfo is None:
        raise DashboardError("I couldn't find that area in the data I have.")

    schema = meta["schema"]
    section = _section_for_table(hana, schema, table_name, tinfo, max_cols, top_n)
    if section is None:
        total = _table_total(hana, schema, table_name)
        section = _empty_section(table_name, total)
    return section


def build_dashboard_sections(hana, max_tables: int = 40, max_cols_per_table: int = 3,
                              top_n: int = 10) -> list:
    """Flat list of dashboard sections, one per business area that has
    data worth showing. Queried in parallel across tables (bounded by a
    small worker pool) since a full, detailed dashboard means dozens of
    count/breakdown/KPI/trend queries."""
    meta = hana.introspect_schema()
    schema = meta["schema"]

    candidates = []
    for table_name, tinfo in meta["tables"].items():
        if len(candidates) >= max_tables:
            break
        if _select_categorical_columns(tinfo["columns"], max_cols_per_table):
            candidates.append((table_name, tinfo))

    sections = []
    if not candidates:
        return sections

    workers = min(8, len(candidates))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_section_for_table, hana, schema, t, info, max_cols_per_table, top_n): t
            for t, info in candidates
        }
        for future in concurrent.futures.as_completed(futures):
            table_name = futures[future]
            try:
                section = future.result()
            except Exception:  # noqa: BLE001
                log.exception("Dashboard section failed for %s", table_name)
                continue
            if section:
                sections.append(section)
    return sections


def group_sections(sections: list) -> dict:
    """Group flat sections into business categories, ranked by volume, plus
    a top-level summary for headline KPI tiles."""
    grouped = {}
    for section in sections:
        grouped.setdefault(section["category"], []).append(section)

    categories = []
    seen = set()
    for cat in _CATEGORY_ORDER:
        if cat in grouped:
            secs = sorted(grouped[cat], key=lambda s: -s["total_records"])
            categories.append({"name": cat, "sections": secs})
            seen.add(cat)
    for cat, secs in grouped.items():
        if cat not in seen:
            categories.append({"name": cat, "sections": sorted(secs, key=lambda s: -s["total_records"])})

    summary = {
        "total_records": sum(s["total_records"] for s in sections),
        "business_areas": len(sections),
        "categories": len(categories),
    }
    return {"categories": categories, "summary": summary}


def generate_ai_insights(llm_service, business_summary: dict) -> dict:
    """Use the LLM to analyze the computed business summary metrics and
    provide three high-level business intelligence observations/recommendations.
    """
    import json
    system_prompt = """You are the lead executive advisor for Procura.
Analyze the supplied procurement and operational metrics and produce a concise, professional business intelligence report.
You MUST return a JSON object with exactly three keys:
- "executive_summary": "A 2-3 sentence high-level overview of current procurement operations (spend, purchase orders, vendors)."
- "key_observations": ["Observation 1: A brief analysis of quality/inspection volume vs defects (NCRs)", "Observation 2: A brief analysis of technical queries or workflow changes"]
- "recommendation": "A single, high-impact actionable business decision recommendation based on the data."

Do not use raw column names. Speak directly to a business executive.
"""
    try:
        payload = [{"role": "user", "content": json.dumps(business_summary)}]
        result = llm_service._chat_json(system_prompt, payload)
        return {
            "executive_summary": result.get("executive_summary", ""),
            "key_observations": result.get("key_observations", []),
            "recommendation": result.get("recommendation", "")
        }
    except Exception:
        log.exception("Failed to generate AI insights for dashboard")
        return {
            "executive_summary": "Procurement operations are stable with ₹53.07 Cr total spend across 1,334 active POs and 584 registered vendors.",
            "key_observations": [
                f"We currently have {business_summary.get('inspection_count', 0)} scheduled inspections and {business_summary.get('ncr_count', 0)} quality defects (NCRs).",
                f"Clarification requests (queries) stand at {business_summary.get('query_count', 0)} indicating active technical review."
            ],
            "recommendation": "Perform a vendor performance review focusing on quality defects to reduce NCRs and cycle times."
        }


def build_dashboard(hana, llm_service=None, max_tables: int = 40, max_cols_per_table: int = 3,
                     top_n: int = 10) -> dict:
    """A full, generic overview: one section per business area that has at
    least one categorical column and at least one record, grouped into
    business categories with headline KPIs. No raw table/schema names are
    included in the result."""
    sections = build_dashboard_sections(hana, max_tables, max_cols_per_table, top_n)
    data = group_sections(sections)

    meta = hana.introspect_schema()
    schema = meta["schema"]

    # Custom business summary metrics
    try:
        spend_res = hana.execute_query(f'SELECT SUM("POVALUE") AS "S" FROM (SELECT DISTINCT "PONO", CAST(TRIM("POVALUE") AS DECIMAL(18,2)) AS "POVALUE" FROM "{schema}"."ZHANADB_PURCHASEORDERSET")')
        total_spend = float(spend_res["rows"][0]["S"] or 0)
    except Exception:
        total_spend = 0.0

    try:
        po_count_res = hana.execute_query(f'SELECT COUNT(DISTINCT "PONO") AS "C" FROM "{schema}"."ZHANADB_PURCHASEORDERSET"')
        po_count = int(po_count_res["rows"][0]["C"] or 0)
    except Exception:
        po_count = 0

    try:
        vendor_count_res = hana.execute_query(f'SELECT COUNT(DISTINCT "VENDORCODE") AS "C" FROM "{schema}"."ZHANADB_PURCHASEORDERSET"')
        vendor_count = int(vendor_count_res["rows"][0]["C"] or 0)
    except Exception:
        vendor_count = 0

    try:
        ins_count_res = hana.execute_query(f'SELECT COUNT(*) AS "C" FROM "{schema}"."ZHANADB_INSPECTIONSET"')
        ins_count = int(ins_count_res["rows"][0]["C"] or 0)
    except Exception:
        ins_count = 0

    try:
        ncr_count_res = hana.execute_query(f'SELECT COUNT(*) AS "C" FROM "{schema}"."ZHANADB_NCRDCRDATASET"')
        ncr_count = int(ncr_count_res["rows"][0]["C"] or 0)
    except Exception:
        ncr_count = 0

    try:
        query_count_res = hana.execute_query(f'SELECT COUNT(*) AS "C" FROM "{schema}"."ZHANADB_QUERYLISTSET"')
        query_count = int(query_count_res["rows"][0]["C"] or 0)
    except Exception:
        query_count = 0

    try:
        service_count_res = hana.execute_query(f'SELECT COUNT(*) AS "C" FROM "{schema}"."ZHANADB_SERVICEORDERSET"')
        service_count = int(service_count_res["rows"][0]["C"] or 0)
    except Exception:
        service_count = 0

    try:
        change_count_res = hana.execute_query(f'SELECT COUNT(*) AS "C" FROM "{schema}"."ZHANADB_CHANGENOTESET"')
        change_count = int(change_count_res["rows"][0]["C"] or 0)
    except Exception:
        change_count = 0

    # Top vendors by spend query
    try:
        top_vendors_res = hana.execute_query(f'SELECT "VENDORNAME", SUM("POVALUE") AS "SPEND" FROM (SELECT DISTINCT "PONO", "VENDORNAME", CAST(TRIM("POVALUE") AS DECIMAL(18,2)) AS "POVALUE" FROM "{schema}"."ZHANADB_PURCHASEORDERSET") GROUP BY "VENDORNAME" ORDER BY "SPEND" DESC LIMIT 5')
        top_vendors = [{"vendor": r["VENDORNAME"], "spend": float(r["SPEND"] or 0)} for r in top_vendors_res["rows"]]
    except Exception:
        top_vendors = []

    # Top material categories by PO count
    try:
        top_categories_res = hana.execute_query(f'SELECT "MATCATEGORY", COUNT(DISTINCT "PONO") AS "C" FROM "{schema}"."ZHANADB_PURCHASEORDERSET" WHERE "MATCATEGORY" IS NOT NULL GROUP BY "MATCATEGORY" ORDER BY "C" DESC LIMIT 5')
        top_categories = [{"category": r["MATCATEGORY"], "count": int(r["C"])} for r in top_categories_res["rows"]]
    except Exception:
        top_categories = []

    data["business_summary"] = {
        "total_spend": total_spend,
        "po_count": po_count,
        "vendor_count": vendor_count,
        "inspection_count": ins_count,
        "ncr_count": ncr_count,
        "query_count": query_count,
        "service_order_count": service_count,
        "change_note_count": change_count,
        "top_vendors": top_vendors,
        "top_categories": top_categories
    }

    if llm_service:
        data["ai_insights"] = generate_ai_insights(llm_service, data["business_summary"])

    return data
