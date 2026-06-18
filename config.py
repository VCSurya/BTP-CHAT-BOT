"""Central configuration. Everything comes from environment variables so no
secret is ever hardcoded. For local development, values are loaded from a
.env file if python-dotenv is installed and a .env file is present.
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv is optional
    pass


def _as_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Config:
    # --- OpenAI ---
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TIMEOUT = _as_int(os.environ.get("OPENAI_TIMEOUT"), 60)

    # --- SAP HANA Cloud ---
    HANA_ADDRESS = os.environ.get("HANA_ADDRESS", "")
    HANA_PORT = _as_int(os.environ.get("HANA_PORT"), 443)
    HANA_USER = os.environ.get("HANA_USER", "")
    HANA_PASSWORD = os.environ.get("HANA_PASSWORD", "")
    HANA_ENCRYPT = _as_bool(os.environ.get("HANA_ENCRYPT"), True)
    HANA_SSL_VALIDATE = _as_bool(os.environ.get("HANA_SSL_VALIDATE"), False)
    # Leave blank to auto-detect via CURRENT_SCHEMA (correct for most HDI users).
    HANA_SCHEMA = os.environ.get("HANA_SCHEMA", "")

    # --- App behaviour ---
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    MAX_RESULT_ROWS = _as_int(os.environ.get("MAX_RESULT_ROWS"), 1000)
    MAX_CHART_POINTS = _as_int(os.environ.get("MAX_CHART_POINTS"), 30)
    # Sample rows pulled per table at startup so the model understands real
    # data. Set SAMPLE_ROWS=0 to disable (e.g. for sensitive data).
    SAMPLE_ROWS = _as_int(os.environ.get("SAMPLE_ROWS"), 3)
    SAMPLE_VALUE_MAXLEN = _as_int(os.environ.get("SAMPLE_VALUE_MAXLEN"), 40)
    POOL_SIZE = _as_int(os.environ.get("HANA_POOL_SIZE"), 4)
    MAX_HISTORY_TURNS = _as_int(os.environ.get("MAX_HISTORY_TURNS"), 8)
    MAX_INPUT_CHARS = _as_int(os.environ.get("MAX_INPUT_CHARS"), 2000)
    MAX_SQL_CHARS = _as_int(os.environ.get("MAX_SQL_CHARS"), 6000)
    SESSION_TTL_SECONDS = _as_int(os.environ.get("SESSION_TTL_SECONDS"), 3600)
    # Whether to return the generated SQL to the client (useful while testing).
    SHOW_SQL = _as_bool(os.environ.get("SHOW_SQL"), True)

    # --- Dashboard (schema-driven overview, no LLM involved) ---
    DASHBOARD_MAX_TABLES = _as_int(os.environ.get("DASHBOARD_MAX_TABLES"), 6)
    DASHBOARD_MAX_COLUMNS = _as_int(os.environ.get("DASHBOARD_MAX_COLUMNS"), 2)
    DASHBOARD_TOP_N = _as_int(os.environ.get("DASHBOARD_TOP_N"), 8)

    @classmethod
    def validate(cls):
        """Return a list of human-readable configuration problems (empty = ok)."""
        problems = []
        if not cls.OPENAI_API_KEY:
            problems.append("OPENAI_API_KEY is not set.")
        if not cls.HANA_ADDRESS:
            problems.append("HANA_ADDRESS is not set.")
        if not cls.HANA_USER:
            problems.append("HANA_USER is not set.")
        if not cls.HANA_PASSWORD:
            problems.append("HANA_PASSWORD is not set.")
        return problems
