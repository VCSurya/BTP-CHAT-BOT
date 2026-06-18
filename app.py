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
import uuid

from flask import Flask, jsonify, render_template, request, session

from config import Config
from prompts.system_prompts import analyst_system, planner_system
from services.chart_service import build_chart
from services.dashboard_service import DashboardError, build_dashboard, build_table_overview
from services.hana_service import HanaService
from services.llm_service import LLMError, LLMService
from services.memory import ConversationMemory
from services.sql_guard import SqlValidationError, validate_select

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
                    if table_name not in meta["tables"]:
                        reply = (
                            "I couldn't find that in the data I have. Could you "
                            "tell me which area you'd like an overview of?"
                        )
                        memory.append(cid, "assistant", reply)
                        return jsonify({"type": "clarify", "reply": reply})
                    overview = build_table_overview(
                        hana, table_name,
                        max_cols=cfg.DASHBOARD_MAX_COLUMNS, top_n=cfg.DASHBOARD_TOP_N,
                    )
                    sections = [overview]
                else:
                    full = build_dashboard(
                        hana,
                        max_tables=cfg.DASHBOARD_MAX_TABLES,
                        max_cols_per_table=cfg.DASHBOARD_MAX_COLUMNS,
                        top_n=cfg.DASHBOARD_TOP_N,
                    )
                    sections = full["sections"]
            except DashboardError as error:
                reply = str(error)
                memory.append(cid, "assistant", reply)
                return jsonify({"type": "clarify", "reply": reply})
            except Exception:  # noqa: BLE001
                log.exception("Overview build failed for table=%r", table_name)
                reply = "I wasn't able to put that overview together just now. Could you try again in a moment?"
                memory.append(cid, "assistant", reply)
                return jsonify({"type": "error", "reply": reply})

            sections = [s for s in sections if s.get("charts")]
            if not sections:
                reply = "There isn't enough data there yet to build an overview."
                memory.append(cid, "assistant", reply)
                return jsonify({"type": "info", "reply": reply})

            total = sum(s.get("total_records", 0) for s in sections)
            reply = (
                f"Here's an overview of {table_name.lower()} — {total:,} records in total."
                if table_name
                else f"Here's an overview of the data — {total:,} records across {len(sections)} areas."
            )
            memory.append(cid, "assistant", reply)
            return jsonify({"type": "dashboard", "reply": reply, "sections": sections})

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
