"""Read-only SQL guard.

This is the security backstop for the natural-language-to-SQL pipeline. The
LLM is *asked* to produce read-only queries, but we never trust that. Every
query passes through here before it touches the database.

Strategy:
  1. Strip out string literals and quoted identifiers so they cannot hide
     forbidden keywords or extra statements (e.g. a column literally named
     "UPDATE" or a value like 'a; drop ...').
  2. Strip comments from that scrubbed copy.
  3. On the scrubbed copy, require the statement to start with SELECT or WITH,
     reject multiple statements, and reject any data-modifying keyword.
  4. Execute the *original* statement (HANA tolerates comments fine).
"""
import re

# Data-modifying / dangerous keywords. Deliberately excludes things that are
# also legitimate SELECT functions in HANA (e.g. REPLACE, SET is not a function
# but is handled by the SELECT-prefix rule).
_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|UPSERT|"
    r"GRANT|REVOKE|CALL|EXEC|EXECUTE|COMMIT|ROLLBACK|IMPORT|EXPORT|"
    r"REORG|UNLOAD|LOAD|RENAME|COMMENT"
    r")\b",
    re.IGNORECASE,
)

_STARTS_OK = re.compile(r"^\s*\(*\s*(SELECT|WITH)\b", re.IGNORECASE)

# Tables that must never be reachable through LLM-generated SQL, no matter
# what the prompt says or how the request is phrased. ZHANADB_USERSET holds
# private user profile data; it is looked up directly by hana_service.fetch_user
# for the signed-in user only, and must never appear in a chat-generated query.
RESTRICTED_TABLES = {"ZHANADB_USERSET"}

_RESTRICTED_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in RESTRICTED_TABLES) + r")\b",
    re.IGNORECASE,
)


class SqlValidationError(Exception):
    """Raised when a generated query is not a safe, read-only single SELECT."""


def _scrub(sql: str) -> str:
    """Replace string literals and double-quoted identifiers with empty markers
    so the structural scan only sees real SQL syntax."""
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)   # 'string literals'
    sql = re.sub(r'"(?:[^"]|"")*"', '""', sql)    # "quoted identifiers"
    return sql


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def validate_select(sql: str, max_chars: int = 6000) -> str:
    """Validate and return the cleaned SQL statement, or raise
    SqlValidationError. The returned string is safe to execute."""
    if not sql or not sql.strip():
        raise SqlValidationError("The query was empty.")

    original = sql.strip()
    if len(original) > max_chars:
        raise SqlValidationError("The query is unusually long and was rejected.")

    # Checked against the raw text (not the scrubbed copy) so a restricted
    # table name can't sneak through inside a quoted identifier.
    restricted = _RESTRICTED_PATTERN.search(original)
    if restricted:
        raise SqlValidationError(
            f"Access to {restricted.group(1).upper()} is not permitted."
        )

    # Statement we will actually run: strip a single trailing semicolon.
    runnable = original.rstrip()
    if runnable.endswith(";"):
        runnable = runnable[:-1].rstrip()

    # Build the scan copy: scrub literals first, then strip comments.
    scan = _strip_comments(_scrub(runnable))

    if ";" in scan:
        raise SqlValidationError("Only a single statement is allowed.")

    if not _STARTS_OK.match(scan):
        raise SqlValidationError("Only read-only SELECT queries are allowed.")

    forbidden = _FORBIDDEN.search(scan)
    if forbidden:
        raise SqlValidationError(
            f"The query contains a disallowed operation: {forbidden.group(1).upper()}."
        )

    return runnable


# Matches `FROM "SCHEMA"."TABLE" alias` / `JOIN "SCHEMA"."TABLE" alias`, with or
# without an `AS` keyword, used to collect every alias the query actually
# introduces.
_ALIAS_DECL = re.compile(
    r'\b(?:FROM|JOIN)\s+"[^"]+"\."[^"]+"\s+(?:AS\s+)?([A-Za-z_]\w*)\b',
    re.IGNORECASE,
)

# Matches `alias."COLUMN"` usages anywhere in the query.
_ALIAS_USE = re.compile(r'\b([A-Za-z_]\w*)\."')


def find_undeclared_aliases(sql: str) -> list:
    """Return any `alias."COLUMN"` references whose alias is never introduced
    by a FROM/JOIN clause in the same statement.

    This is the LLM's most common self-inflicted failure mode: it writes
    `mf."MATERIALFAMILY"` while forgetting to actually JOIN a `mf` table, which
    HANA rejects with an opaque "invalid column name" error. Catching it here
    avoids a wasted round trip to the database and gives the repair prompt an
    exact, actionable alias name instead of a raw HANA error.

    Unlike validate_select's scan copy, double-quoted identifiers are kept
    intact here (only comments and string literals are stripped) because the
    table/alias names inside them are exactly what this check needs to read.
    """
    scan = _strip_comments(re.sub(r"'(?:[^']|'')*'", "''", sql))
    declared = {m.group(1).upper() for m in _ALIAS_DECL.finditer(scan)}
    used = {m.group(1).upper() for m in _ALIAS_USE.finditer(scan)}
    return sorted(used - declared)
