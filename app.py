"""Procura — Procurement Analytics Chatbot (Flask + SAP HANA Cloud + GPT-4o-mini).

Request pipeline for /api/chat:
    1. Validate and bound the user message.
    2. Load the (cached) live schema and recent conversation history.
    3. Stage 1 (planner): classify -> greeting / out_of_scope / clarify / data_query.
    4. For data_query: validate the SQL is read-only, execute it (row-capped).
    5. Stage 2 (analyst): turn real rows into an insight + chart spec.
    6. Build a Chart.js spec from the real rows and return everything as JSON.

Every failure mode returns a friendly message to the user (HTTP 200) while the
technical detail is logged server-side. Raw errors and credentials are never
exposed to the client.
"""
import logging
import os
import re
import uuid

from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS 
from config import Config
from prompts.system_prompts import analyst_system, planner_system
from prompts.table_knowledge import TABLE_ALIASES
from services.chart_service import build_chart
from services.dashboard_service import (
    DashboardError,
    build_dashboard,
    build_dashboard_sections,
    build_table_overview,
    friendly_name,
    group_sections,
)
from services.hana_service import HanaService
from services.llm_service import LLMError, LLMService
from services.memory import ConversationMemory
from services.sql_guard import SqlValidationError, validate_select

app = Flask(__name__)

CORS(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("procura")


def _fallback_answer(result: dict) -> str:
    rows = result.get("rows", [])
    if not rows:
        return (
            "I couldn't find anything matching that. Could you try rephrasing, "
            "or ask about something else?"
        )
    return "Here's what I found."


def _build_recent_context(last_query: dict) -> str:
    """Describe the previous data query so the planner can extend follow-ups."""
    if not last_query:
        return ""
    columns = ", ".join(last_query.get("columns", [])) or "(none)"
    chart_note = ""
    prev_type = (last_query.get("viz") or {}).get("type")
    if prev_type and prev_type != "none":
        chart_note = f"The previous answer was shown as a {prev_type} chart.\n"
    return (
        f'The user\'s previous data question was: "{last_query.get("question", "")}".\n'
        f"It was answered by running this SQL:\n{last_query.get('sql', '')}\n"
        f"That query returned these columns: {columns}.\n"
        f"{chart_note}"
        "If the new message builds on this (it says 'also', 'and', 'what about', "
        "'for those', 'include', or omits its subject), treat it as a follow-up: "
        "reuse the tables, JOINs, and filters above and extend the query, keeping the "
        "original columns unless the user asks to drop them. If the new message asks "
        "to see this same data in a different chart, use the 'rechart' intent."
    )


def _normalize_table_token(name: str) -> str:
    """Strip the ZHANADB_ prefix, a trailing SET, and non-alnum noise so
    near-miss table names (wrong case, missing prefix, plural mismatch)
    still compare equal."""
    token = re.sub(r"[^A-Za-z0-9]", "", (name or "")).upper()
    if token.startswith("ZHANADB"):
        token = token[len("ZHANADB"):]
    if token.endswith("SET"):
        token = token[: -len("SET")]
    return token


def _resolve_table_name(name: str, tables: dict) -> str | None:
    """Match a (possibly imperfect) table name from the LLM against the real,
    live schema. Tries an exact match first, then a normalized match (case,
    missing prefix/suffix), then known business-word aliases. Returns the
    real table name, or None if nothing reasonable matches."""
    if not name:
        return None
    name = name.strip()
    if name in tables:
        return name

    upper = name.upper()
    for real in tables:
        if real.upper() == upper:
            return real

    target = _normalize_table_token(name)
    if target:
        for real in tables:
            if _normalize_table_token(real) == target:
                return real

    lowered = name.lower()
    for real, synonyms in TABLE_ALIASES.items():
        if real in tables and any(
            lowered == syn or lowered in syn or syn in lowered for syn in synonyms
        ):
            return real

    return None


_TABLE_REF_RE = re.compile(r'"(ZHANADB_[A-Za-z0-9_]+)"')


def _unknown_tables_in_sql(sql: str, tables: dict) -> list:
    """Return any ZHANADB_* identifiers referenced in the generated SQL that
    do not exist in the live schema -- a sign the model hallucinated a table
    name rather than copying one from the real schema."""
    known_upper = {t.upper() for t in tables}
    seen = []
    for ref in _TABLE_REF_RE.findall(sql or ""):
        if ref.upper() not in known_upper and ref not in seen:
            seen.append(ref)
    return seen


def _available_areas_text(tables: dict, search_term: str = None) -> str:
    from services.dashboard_service import friendly_name
    if search_term:
        term = search_term.strip().lower().rstrip('s')
        matches = []
        for t in tables:
            f_name = friendly_name(t)
            if term in f_name.lower() or term in t.lower():
                matches.append(f_name)
        if matches:
            return ", ".join(matches[:5])

    # Curated key business domains
    curated = [
        "ZHANADB_PURCHASEORDERSET",
        "ZHANADB_INSPECTIONSET",
        "ZHANADB_SERVICEORDERSET",
        "ZHANADB_CHANGENOTESET",
        "ZHANADB_QUERYLISTSET",
        "ZHANADB_NCRDCRDATASET",
        "ZHANADB_MATERIALSET",
        "ZHANADB_PROJECTWBSSET",
    ]
    names = []
    for t in curated:
        if t in tables:
            names.append(friendly_name(t))
    if not names:
        names = [friendly_name(t) for t in list(tables.keys())[:6]]
    return ", ".join(names[:6])


def create_app() -> Flask:
    app = Flask(__name__)
    cfg = Config()
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["JSON_SORT_KEYS"] = False

    problems = cfg.validate()
    if problems:
        for problem in problems:
            log.warning("Config: %s", problem)

    hana = HanaService(cfg)
    llm = LLMService(cfg)
    memory = ConversationMemory(
        max_turns=cfg.MAX_HISTORY_TURNS, ttl_seconds=cfg.SESSION_TTL_SECONDS
    )

    def _conversation_id() -> str:
        cid = session.get("cid")
        if not cid:
            cid = uuid.uuid4().hex
            session["cid"] = cid
        return cid

    # --- pages -----------------------------------------------------------
    @app.get("/")
    def index():
        return render_template("index.html")

    # --- ops endpoints ---------------------------------------------------
    @app.get("/api/health")
    def health():
        database = "up"
        try:
            hana.execute_query('SELECT 1 AS "OK" FROM DUMMY', max_rows=1)
        except Exception as error:  # noqa: BLE001 - report, don't crash
            database = f"down ({type(error).__name__})"
        return jsonify(
            {
                "status": "ok",
                "database": database,
                "model": cfg.OPENAI_MODEL,
                "config_problems": cfg.validate(),
            }
        )

    @app.post("/api/schema/refresh")
    def refresh_schema():
        try:
            meta = hana.introspect_schema(refresh=True)
            return jsonify(
                {"schema": meta["schema"], "objects": list(meta["tables"].keys())}
            )
        except Exception:  # noqa: BLE001
            log.exception("Schema refresh failed")
            return jsonify({"error": "Could not read the schema from the database."}), 500

    @app.post("/api/reset")
    def reset():
        memory.clear(_conversation_id())
        return jsonify({"status": "cleared"})

    # --- user identity ---------------------------------------------------
    @app.post("/api/user/identify")
    def identify_user():
        """Accept a user ID, look them up in ZHANADB_USERSET, and store
        their profile in the session so every subsequent chat message
        can be personalised.  Returns the user profile (minus any
        sensitive fields the front-end doesn't need)."""
        data = request.get_json(silent=True) or {}
        user_id = (data.get("userId") or "").strip()
        if not user_id:
            return jsonify({"error": "userId is required."}), 400

        profile = hana.fetch_user(user_id)
        if profile is None:
            return jsonify({"error": "User not found."}), 404

        # Store in session so chat() can use it.
        session["user_profile"] = profile
        session["user_id"] = user_id
        log.info("User identified: %s", user_id)
        return jsonify({"status": "ok", "profile": profile})

    @app.get("/api/dashboard")
    def dashboard():
        try:
            data = build_dashboard(
                hana,
                llm_service=llm,
                max_tables=cfg.DASHBOARD_MAX_TABLES,
                max_cols_per_table=cfg.DASHBOARD_MAX_COLUMNS,
                top_n=cfg.DASHBOARD_TOP_N,
            )
        except Exception:  # noqa: BLE001
            log.exception("Dashboard build failed")
            return jsonify({"error": "Could not build the dashboard right now."}), 500
        return jsonify(data)

    # --- chat ------------------------------------------------------------
    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"error": "Please type a question."}), 400
        if len(user_message) > cfg.MAX_INPUT_CHARS:
            user_message = user_message[: cfg.MAX_INPUT_CHARS]

        cid = _conversation_id()
        history = memory.get(cid)

        # Load the live schema (cached after first call).
        try:
            schema_prompt = hana.schema_prompt()
        except Exception:  # noqa: BLE001
            log.exception("Schema introspection failed")
            return jsonify(
                {
                    "type": "error",
                    "reply": "I'm having trouble accessing the information right "
                    "now. Please try again in a moment.",
                }
            )

        # Stage 1: plan.
        recent_context = _build_recent_context(memory.get_last_query(cid))
        try:
            user_profile = session.get("user_profile")
            plan = llm.plan(
                planner_system(schema_prompt, recent_context, user_profile=user_profile),
                history, user_message,
            )
        except LLMError:
            return jsonify(
                {
                    "type": "error",
                    "reply": "I didn't quite catch that. Could you say it a "
                    "different way?",
                }
            )

        memory.append(cid, "user", user_message)
        intent = (plan.get("intent") or "").lower()

        if intent in ("greeting", "out_of_scope"):
            reply = plan.get("reply") or (
                "I'm here to help with your procurement data — try asking about "
                "purchase orders, vendors, inspections, dispatches, or payments."
            )
            memory.append(cid, "assistant", reply)
            return jsonify({"type": intent, "reply": reply})

        if intent == "clarify":
            question = plan.get("clarifying_question") or (
                "Could you give me a little more detail so I can pull the right data?"
            )
            memory.append(cid, "assistant", question)
            return jsonify({"type": "clarify", "reply": question})

        if intent == "overview":
            table_name = (plan.get("overview_table") or "").strip()
            try:
                if table_name:
                    meta = hana.introspect_schema()
                    resolved_table = _resolve_table_name(table_name, meta["tables"])
                    if resolved_table is None:
                        options = _available_areas_text(meta["tables"], search_term=table_name)
                        if options:
                            reply = (
                                f"I couldn't find a direct match for '{table_name}' in the data. "
                                f"Did you mean one of these: {options}?"
                            )
                        else:
                            reply = (
                                f"I couldn't find '{table_name}' in the data. I can show you overviews for "
                                "Purchase Orders, Quality Inspections, Service Orders, Change Notes, or Materials — "
                                "which would you like?"
                            )
                        memory.append(cid, "assistant", reply)
                        return jsonify({"type": "clarify", "reply": reply})
                    table_name = resolved_table
                    overview = build_table_overview(
                        hana, table_name,
                        max_cols=cfg.DASHBOARD_MAX_COLUMNS, top_n=cfg.DASHBOARD_TOP_N,
                    )
                    flat_sections = [overview] if overview.get("charts") else []

                    if not flat_sections:
                        reply = "There isn't enough data there yet to build an overview."
                        memory.append(cid, "assistant", reply)
                        return jsonify({"type": "info", "reply": reply})

                    grouped = group_sections(flat_sections)
                    summary = grouped["summary"]
                    reply = f"Here's an overview of {flat_sections[0]['name']} — {summary['total_records']:,} records in total."
                    memory.append(cid, "assistant", reply)
                    return jsonify(
                        {
                            "type": "dashboard",
                            "reply": reply,
                            "summary": summary,
                            "categories": grouped["categories"],
                        }
                    )
                else:
                    full = build_dashboard(
                        hana,
                        llm_service=llm,
                        max_tables=cfg.DASHBOARD_MAX_TABLES,
                        max_cols_per_table=cfg.DASHBOARD_MAX_COLUMNS,
                        top_n=cfg.DASHBOARD_TOP_N,
                    )
                    categories = full.get("categories") or []
                    if not categories:
                        reply = "There isn't enough data there yet to build a dashboard."
                        memory.append(cid, "assistant", reply)
                        return jsonify({"type": "info", "reply": reply})

                    summary = full.get("summary") or {}
                    reply = f"Here's an overview of the business — {summary.get('total_records', 0):,} records across {summary.get('business_areas', 0)} areas."
                    memory.append(cid, "assistant", reply)

                    response_payload = {
                        "type": "dashboard",
                        "reply": reply,
                        "summary": summary,
                        "categories": categories,
                    }
                    if "business_summary" in full:
                        response_payload["business_summary"] = full["business_summary"]
                    if "ai_insights" in full:
                        response_payload["ai_insights"] = full["ai_insights"]
                    return jsonify(response_payload)
            except DashboardError as error:
                reply = str(error)
                memory.append(cid, "assistant", reply)
                return jsonify({"type": "clarify", "reply": reply})
            except Exception:  # noqa: BLE001
                log.exception("Overview build failed for table=%r", table_name)
                reply = "I wasn't able to put that overview together just now. Could you try again in a moment?"
                memory.append(cid, "assistant", reply)
                return jsonify({"type": "error", "reply": reply})

        if intent == "rechart":
            last = memory.get_last_query(cid)
            if not last or not last.get("rows"):
                reply = (
                    "I don't have anything to chart just yet — ask me about your "
                    "procurement data first, then I can show it in different chart "
                    "styles."
                )
                memory.append(cid, "assistant", reply)
                return jsonify({"type": "info", "reply": reply})

            new_type = (plan.get("chart_type") or "").lower()
            viz = dict(last.get("viz") or {})
            if new_type in ("bar", "line", "pie", "doughnut"):
                viz["type"] = new_type
            elif viz.get("type", "none") == "none":
                viz["type"] = "bar"

            prior = {"columns": last["columns"], "rows": last["rows"]}
            chart = build_chart(prior, viz, cfg.MAX_CHART_POINTS)
            if not chart:
                reply = (
                    "This one doesn't really work as a chart — it isn't a set of "
                    "categories with numbers. Here's the information instead."
                )
                memory.append(cid, "assistant", reply)
                return jsonify(
                    {
                        "type": "data",
                        "reply": reply,
                        "chart": None,
                        "table": {
                            "columns": last["columns"],
                            "rows": last["rows"][:100],
                        },
                        "row_count": last.get("row_count", len(last["rows"])),
                        "sql": last["sql"] if cfg.SHOW_SQL else None,
                    }
                )

            reply = f"Here's the same data as a {chart['type']} chart."
            memory.set_last_query(
                cid, last["question"], last["sql"], last["columns"],
                rows=last["rows"], viz=viz, row_count=last.get("row_count"),
            )
            memory.append(cid, "assistant", reply)
            return jsonify(
                {
                    "type": "data",
                    "reply": reply,
                    "chart": chart,
                    "table": {
                        "columns": last["columns"],
                        "rows": last["rows"][:100],
                    },
                    "row_count": last.get("row_count", len(last["rows"])),
                    "sql": last["sql"] if cfg.SHOW_SQL else None,
                }
            )

        # intent == data_query (default path)
        sql = plan.get("sql") or ""
        enhanced_question = plan.get("enhanced_question") or user_message
        try:
            safe_sql = validate_select(sql, max_chars=cfg.MAX_SQL_CHARS)
        except SqlValidationError as error:
            log.warning("Rejected SQL (%s): %s", error, sql)
            reply = (
                "I'm not sure how to look that up — could you tell me a bit more "
                "about what you'd like to see?"
            )
            memory.append(cid, "assistant", reply)
            return jsonify({"type": "error", "reply": reply})

        try:
            meta = hana.introspect_schema()
            unknown_tables = _unknown_tables_in_sql(safe_sql, meta["tables"])
        except Exception:  # noqa: BLE001
            unknown_tables = []
        if unknown_tables:
            log.warning(
                "Generated SQL referenced unknown table(s) %s: %s",
                unknown_tables, safe_sql,
            )
            options = _available_areas_text(meta["tables"])
            reply = (
                "I don't have information on that specific area, but I can help with "
                f"things like {options}, and more — could you tell me a bit more about "
                "what you're looking for?"
            )
            memory.append(cid, "assistant", reply)
            return jsonify({"type": "clarify", "reply": reply})

        try:
            result = hana.execute_query(safe_sql, max_rows=cfg.MAX_RESULT_ROWS)
        except Exception:  # noqa: BLE001
            log.exception("Query execution failed for SQL: %s", safe_sql)
            reply = (
                "I wasn't able to pull that up — it might be something I don't have "
                "information on. Could you rephrase it, or ask about something else?"
            )
            memory.append(cid, "assistant", reply)
            return jsonify({"type": "error", "reply": reply})

        # Stage 2: analyze.
        try:
            analysis = llm.analyze(
                analyst_system(), user_message, safe_sql, result,
                schema_summary=hana.schema_summary(),
                enhanced_question=enhanced_question,
            )
        except LLMError:
            analysis = {"answer": _fallback_answer(result), "viz": {"type": "none"}}

        answer = analysis.get("answer") or _fallback_answer(result)
        viz = analysis.get("viz") or {}
        chart = build_chart(result, viz, cfg.MAX_CHART_POINTS)
        memory.append(cid, "assistant", answer)
        # Keep a bounded copy of the result so the user can re-chart it later
        # without re-running the query.
        memory.set_last_query(
            cid,
            user_message,
            safe_sql,
            result["columns"],
            rows=result["rows"][:300],
            viz=viz,
            row_count=len(result["rows"]),
        )

        return jsonify(
            {
                "type": "data",
                "reply": answer,
                "chart": chart,
                "table": {
                    "columns": result["columns"],
                    "rows": result["rows"][:100],
                },
                "row_count": len(result["rows"]),
                "truncated": result.get("truncated", False),
                "sql": safe_sql if cfg.SHOW_SQL else None,
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
