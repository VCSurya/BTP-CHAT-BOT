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
import random
import re
import uuid

from flask import Flask, jsonify, render_template, request, session
from flask_cors import CORS 
from config import Config
from prompts.system_prompts import analyst_system, planner_system
from prompts.table_knowledge import TABLE_ALIASES
from services.chart_service import build_chart, infer_columns
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
from services.sql_guard import SqlValidationError, find_undeclared_aliases, validate_select

app = Flask(__name__)

CORS(app, supports_credentials=True)

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


def _attempt_sql_repair(llm, system_prompt: str, user_message: str,
                         failed_sql: str, error) -> dict | None:
    """One self-correction pass: feed the exact DB error back to the planner
    so it can re-read the schema and fix a wrong column/table name, instead
    of giving up after a single bad guess. Returns a fresh plan dict, or
    None if the repair call itself fails."""
    repair_message = (
        f"{user_message}\n\n"
        "[SYSTEM NOTE: Your previous SQL for this question failed against the "
        f"real database with this error: {error}\n"
        f"The failed SQL was: {failed_sql}\n"
        "Re-check the schema above very carefully and find the column/table that "
        "actually exists for what was meant (check any 'Column notes' for the "
        "table too). Return a corrected plan. If nothing in the schema truly "
        "matches, use intent \"clarify\" instead of guessing again.]"
    )
    try:
        return llm.plan(system_prompt, [], repair_message)
    except LLMError:
        return None


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


COLLAPSED_GREETINGS = {
    "hi", "helo", "hey", "hola", "greting", "gretings", "god morning", "god afternoon", "god evening",
    "afternon", "evening", "howdy", "yo", "namaste", "god day", "thanks", "thank", "wasup", "sup", "hlo", "hlw"
}

CONVERSATIONAL_GREETINGS = {
    "how are you",
    "how are you doing",
    "how is it going",
    "hows it going",
    "whats up",
    "what up",
    "wassup",
    "how do you do",
    "who are you",
    "what are you",
    "what is your name",
}

def _detect_greeting(message: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", message).strip().lower()
    if not cleaned:
        return False
        
    address_words = {"bot", "procura", "assistant", "there", "everyone", "all", "system"}
    words = cleaned.split()
    filtered_words = [w for w in words if w not in address_words]
    if not filtered_words:
        return False
        
    cleaned_filtered = " ".join(filtered_words)
    if cleaned_filtered in CONVERSATIONAL_GREETINGS:
        return True
        
    def collapse(w):
        return re.sub(r"(.)\1+", r"\1", w)
        
    collapsed_words = [collapse(w) for w in filtered_words]
    if len(collapsed_words) == 1:
        return collapsed_words[0] in COLLAPSED_GREETINGS
        
    if len(collapsed_words) == 2:
        comb = f"{collapsed_words[0]} {collapsed_words[1]}"
        return comb in COLLAPSED_GREETINGS
        
    return False


def _extract_user_greeting(message: str) -> tuple[str, str, int]:
    cleaned = re.sub(r"[^\w\s]", "", message).strip().lower()
    words = cleaned.split()
    if not words:
        return "", "", 0
    
    first_word = words[0]
    
    def collapse(w):
        return re.sub(r"(.)\1+", r"\1", w)
    
    collapsed = collapse(first_word)
    if collapsed not in COLLAPSED_GREETINGS:
        found_stem = None
        for stem in ("hi", "hello", "hey", "hola", "howdy", "yo", "sup", "hlo", "hlw"):
            if first_word.startswith(stem):
                found_stem = stem
                break
        if not found_stem:
            return "", "", 0
        collapsed = found_stem
        
    match = re.search(r"((.)\2{2,})$", first_word)
    if match:
        repeating_seq = match.group(1)
        repeating_char = match.group(2)
        return collapsed, repeating_char, len(repeating_seq)
    
    return collapsed, "", 1


def _generate_matching_greeting(collapsed: str, repeating_char: str, repeat_count: int, name: str = "") -> str:
    base = "Hello"
    if collapsed == "hi":
        base = "Hi"
    elif collapsed == "hey":
        base = "Hey"
    elif collapsed == "yo":
        base = "Yo"
    elif collapsed == "hola":
        base = "Hola"
    elif collapsed == "howdy":
        base = "Howdy"
    elif collapsed in ("hlo", "hlw"):
        base = "Hello"
        
    count = min(repeat_count, 8)
    
    if repeating_char and count >= 3:
        if base == "Hi" and repeating_char == "i":
            exaggerated = "H" + "i" * count
        elif base == "Hey" and repeating_char == "y":
            exaggerated = "He" + "y" * count
        elif base == "Hello" and repeating_char == "o":
            exaggerated = "Hell" + "o" * count
        else:
            exaggerated = base + repeating_char * (count - 1)
    else:
        exaggerated = base
        
    if name:
        return f"{exaggerated} {name}! 👋"
    return f"{exaggerated}! 👋"


def _generate_conversational_reply(cleaned_message: str, user_profile: dict = None) -> str:
    name = ""
    if user_profile:
        name = user_profile.get("FIRSTNAME", "") or user_profile.get("NAME", "") or user_profile.get("USERNAME", "") or user_profile.get("USER_NAME", "")
        if name:
            name = name.strip().split()[0].title()
            
    greeting = f"Hi {name}! 👋" if name else "Hello! 👋"
    
    if any(q in cleaned_message for q in ("how are you", "how is it going", "hows it going", "how do you do")):
        return (
            f"{greeting} I'm doing great, thank you for asking! 😊 I am **Adani Procura**, your procurement intelligence copilot. "
            "I'm fully connected to the SAP HANA database and ready to run query visualizations.\n\n"
            "How can I assist you with your data analysis today?"
        )
        
    if any(q in cleaned_message for q in ("who are you", "what are you", "your name")):
        return (
            f"I am **Adani Procura**, your dedicated enterprise procurement intelligence assistant. 🤖\n\n"
            "I can run live database queries, analyze suppliers, track quality inspections, and build dashboards "
            "directly from your SAP environment.\n\n"
            "What dataset or metric can I pull up for you?"
        )
        
    if any(q in cleaned_message for q in ("whats up", "what up", "wassup")):
        return (
            f"{greeting} Not much! Just ready and waiting to crunch some database numbers for you. 📊\n\n"
            "You can ask me to analyze purchase orders, check vendor defect rates, or show you the Executive Dashboard."
        )
        
    return ""


def _generate_greeting_reply(user_message: str, user_profile: dict = None) -> str:
    cleaned = re.sub(r"[^\w\s]", "", user_message).strip().lower()
    conv_reply = _generate_conversational_reply(cleaned, user_profile)
    if conv_reply:
        return conv_reply
        
    name = ""
    if user_profile:
        name = user_profile.get("FIRSTNAME", "") or user_profile.get("NAME", "") or user_profile.get("USERNAME", "") or user_profile.get("USER_NAME", "")
        if name:
            name = name.strip().split()[0].title()
            
    collapsed, rep_char, rep_count = _extract_user_greeting(user_message)
    greeting = _generate_matching_greeting(collapsed, rep_char, rep_count, name)
    
    templates = [
        f"{greeting} I'm **Adani Procura**, your AI-powered procurement intelligence assistant. "
        "I'm ready to query your SAP database and visualize the results.\n\n"
        "Here are a few examples of what you can ask me to do:\n"
        "* *\"Top 10 vendors by total PO value\"*\n"
        "* *\"Show me PO status distribution\"*\n"
        "* *\"How many inspections occurred this month?\"*\n\n"
        "What data would you like to analyze today?",
        
        f"{greeting} Welcome to the Adani Procurement Analytics Portal. "
        "I can help you monitor spend, analyze vendors, track quality inspections, and build dashboards in real-time.\n\n"
        "Feel free to ask questions like:\n"
        "* *\"Give me an overview of all materials\"*\n"
        "* *\"Show dispatch status summary\"*\n"
        "* *\"Which suppliers have the most NCR defects?\"*\n\n"
        "How can I assist you with your queries today?",
        
        f"{greeting} I'm **Adani Procura**, your personal procurement-analytics ally. "
        "I'm connected to the live database and can build charts and dashboards instantly.\n\n"
        "Try asking me one of these:\n"
        "* *\"Show me the full data dashboard\"*\n"
        "* *\"Top suppliers by spend\"*\n"
        "* *\"PO status breakdown\"*\n\n"
        "What analytics reports can I pull for you?",

        f"{greeting} Great to connect with you! I am **Adani Procura**, ready to parse and visualize your procurement datasets.\n\n"
        "What report can I run for you? You can ask me to inspect:\n"
        "* *\"Inspections pending dispatch approval\"*\n"
        "* *\"NCR counts grouped by vendor name\"*\n"
        "* *\"Active PO values for this quarter\"*\n\n"
        "Let's get started!",

        f"{greeting} Glad you stopped by! I'm **Adani Procura**, your procurement copilot. "
        "I can build custom bar charts, pie charts, and data tables on the fly.\n\n"
        "Would you like to search vendor metrics, check dispatch progress, or inspect POs today?",

        f"{greeting} Hello! I am **Adani Procura**, your assistant for all things procurement. "
        "How can I help you extract insights from the SAP HANA database today?",

        f"{greeting} **System online and ready!** 🚀 I'm your dedicated procurement assistant. "
        "I can analyze purchase orders, material dispatches, and quality inspections in seconds.\n\n"
        "Try saying: *\"Show me vendor performance\"* or *\"Chart monthly order values\"*.",

        f"{greeting} Connection to the SAP HANA database is healthy and ready to fetch insights! ⚡ "
        "I can build real-time visual reports of your procurement pipeline.\n\n"
        "Would you like me to load the Executive Dashboard or query a specific table?",

        f"{greeting} Procura system initialized. 📊 Let's turn your raw database tables into beautiful charts and insights.\n\n"
        "What area are we focusing on today? Purchase Orders, Suppliers, Materials, or Inspections?",

        f"{greeting} Welcome! I make navigating complex procurement tables easy. "
        "Just ask me your question in plain English, and I'll handle the SQL and visualization.\n\n"
        "What analysis shall we run first?",

        f"{greeting} Nice to meet you! I'm **Adani Procura**. I specialize in real-time supply chain analytics and spend monitoring.\n\n"
        "Ask me to *\"show the summary dashboard\"* to get a high-level view, or query a specific metric!",

        f"{greeting} How's it going? I'm your procurement intelligence copilot. "
        "I can check dispatch logs, identify top suppliers, and audit inspection results.\n\n"
        "What data can I retrieve for you right now?"
    ]
    
    return random.choice(templates)


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
                "provider": cfg.LLM_PROVIDER,
                "model": cfg.active_model(),
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
        user_profile = session.get("user_profile")

        # Intercept simple greetings to reply immediately and save cost/latency
        if _detect_greeting(user_message):
            reply = _generate_greeting_reply(user_message, user_profile)
            memory.append(cid, "user", user_message)
            memory.append(cid, "assistant", reply)
            return jsonify({"type": "greeting", "reply": reply})

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

            # The previous answer may have been shown as a plain table (no
            # label/value mapping was ever picked, e.g. viz.type was "none").
            # Re-derive a mapping straight from the real data instead of
            # forcing a chart type with nothing to plot.
            if not viz.get("label_column") or not viz.get("value_columns"):
                inferred_label, inferred_values = infer_columns(
                    last["columns"], last["rows"]
                )
                if not viz.get("label_column"):
                    viz["label_column"] = inferred_label
                if not viz.get("value_columns"):
                    viz["value_columns"] = inferred_values

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
            undeclared = find_undeclared_aliases(safe_sql)
            if undeclared:
                raise ValueError(
                    "invalid column name: table alias(es) "
                    + ", ".join(undeclared)
                    + " are referenced (e.g. " + undeclared[0] + '."COLUMN") but never '
                    "introduced via a FROM/JOIN clause in this statement."
                )
            result = hana.execute_query(safe_sql, max_rows=cfg.MAX_RESULT_ROWS)
        except Exception as exec_error:  # noqa: BLE001
            log.warning("Query execution failed for SQL: %s", safe_sql, exc_info=True)
            # One self-correction attempt: feed the real DB error back to the
            # planner so it can fix a wrong column/table guess instead of
            # immediately telling the user it failed.
            repaired_plan = _attempt_sql_repair(
                llm,
                planner_system(schema_prompt, recent_context, user_profile=user_profile),
                user_message, safe_sql, exec_error,
            )
            result = None
            if repaired_plan and (repaired_plan.get("intent") or "").lower() == "data_query":
                try:
                    repaired_sql = validate_select(repaired_plan.get("sql") or "", max_chars=cfg.MAX_SQL_CHARS)
                    repaired_undeclared = find_undeclared_aliases(repaired_sql)
                    if repaired_undeclared:
                        raise ValueError(
                            "invalid column name: table alias(es) "
                            + ", ".join(repaired_undeclared)
                            + " are still referenced without a FROM/JOIN clause."
                        )
                    result = hana.execute_query(repaired_sql, max_rows=cfg.MAX_RESULT_ROWS)
                    safe_sql = repaired_sql
                    enhanced_question = repaired_plan.get("enhanced_question") or enhanced_question
                except Exception:  # noqa: BLE001
                    log.exception("Repaired SQL also failed: %s", repaired_plan.get("sql"))
                    result = None
            elif repaired_plan and (repaired_plan.get("intent") or "").lower() == "clarify":
                question = repaired_plan.get("clarifying_question") or (
                    "Could you give me a little more detail so I can pull the right data?"
                )
                memory.append(cid, "assistant", question)
                return jsonify({"type": "clarify", "reply": question})

            if result is None:
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
