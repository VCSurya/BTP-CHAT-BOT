# Procura — Procurement Analytics Chatbot

A ChatGPT-style assistant over your SAP HANA Cloud procurement data. Ask questions
in plain language; Procura classifies the request, generates a **read-only** HANA
SQL query, runs it, explains the result like an analyst, and draws an interactive
chart — all grounded in your **live** database schema.

Stack: **Flask** (Python) · **SAP HANA Cloud** (`hdbcli`) · **OpenAI GPT-4o-mini** ·
**Chart.js** (client-side, interactive).

---

## Security first

If your HANA password (or any credential) has ever been shared in plain text
— including pasted into a chat — **rotate it now**. This project loads every
secret from environment variables and never hardcodes them. Keep your real
values in a local `.env` (git-ignored) or your platform's credential store.

---

## Quick start (local)

```bash
cd procura
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env with your real values
python app.py               # serves on http://localhost:5000
```

Open `http://localhost:5000` and start asking questions. The status dot in the
top-right turns green once the database connection is verified.

### Health check

```bash
curl http://localhost:5000/api/health
```

Returns the database status, the model in use, and any missing configuration.

---

## How it works

Each message runs through a two-stage pipeline:

1. **Planner (LLM).** Given the live schema and recent conversation, it decides
   the intent — *greeting*, *out of scope*, *needs clarification*, or *data
   question* — and, for data questions, writes a single read-only `SELECT` in
   HANA's SQL dialect using your exact, schema-qualified table and column names.
2. **SQL guard (deterministic).** Before anything touches the database, the
   query is verified to be a single, read-only `SELECT`/`WITH`. String literals
   and quoted identifiers are scrubbed first, then the statement is checked for
   stacked statements and any data-modifying keyword. Anything else is rejected.
3. **Execution.** The query runs through a small connection pool with one
   automatic retry on transient disconnects, capped at `MAX_RESULT_ROWS`.
4. **Analyst (LLM).** Given the **real** returned rows, it writes a concise,
   insight-first answer and picks a chart type plus the label/value columns.
5. **Chart build (deterministic).** The Chart.js spec is assembled in Python
   from the real rows, so chart values can never be hallucinated.

Conversation context is held per browser session so follow-ups like *"and for
last quarter?"* work.

### Why these choices

- **Live schema introspection** (`SYS.TABLE_COLUMNS`, `SYS.VIEW_COLUMNS`,
  `SYS.REFERENTIAL_CONSTRAINTS`) means the bot always matches your real tables —
  no schema file to maintain. It's cached at first use; refresh with
  `POST /api/schema/refresh`.
- **Read-only by construction.** The SQL guard is the backstop, but for true
  defense-in-depth, point `HANA_USER` at a database user with only `SELECT`
  privileges.
- **Client-side Chart.js** keeps the backend light (no image rendering) and the
  charts interactive.

---

## Configuration

All settings come from environment variables — see `.env.example`. Key ones:

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI key | — (required) |
| `OPENAI_MODEL` | Model name | `gpt-4o-mini` |
| `HANA_ADDRESS` / `HANA_PORT` | HANA Cloud endpoint | — / `443` |
| `HANA_USER` / `HANA_PASSWORD` | DB credentials | — (required) |
| `HANA_SCHEMA` | Schema to introspect | blank → `CURRENT_SCHEMA` |
| `MAX_RESULT_ROWS` | Row cap per query | `1000` |
| `MAX_CHART_POINTS` | Points drawn on a chart | `30` |
| `SHOW_SQL` | Return generated SQL to the UI | `true` |

---

## API

| Method & path | Description |
| --- | --- |
| `POST /api/chat` | `{ "message": "..." }` → answer, chart, table, sql |
| `GET /api/health` | DB + model status |
| `POST /api/schema/refresh` | Re-read the live schema |
| `POST /api/reset` | Clear the current conversation |

---

## Deploy to SAP BTP (Cloud Foundry)

```bash
cf push procura -m 512M --no-route          # uses the included Procfile
cf set-env procura OPENAI_API_KEY "..."     # set each secret as an env var
cf set-env procura HANA_ADDRESS  "..."
# ...repeat for HANA_USER, HANA_PASSWORD, FLASK_SECRET_KEY, etc.
cf map-route procura <your-domain> --hostname procura
cf restage procura
```

`gunicorn` (in `Procfile`) serves the app in production.

---

## Notes & next steps

- Conversation memory is process-local. For multiple instances, swap
  `ConversationMemory` for Redis (same `get` / `append` / `clear` interface).
- For per-user data isolation, add authentication and inject a row-level filter
  into the planner prompt (your schema includes a `USERS` table to key off).
- To extend domain understanding, expand the vocabulary block in
  `prompts/system_prompts.py`.
