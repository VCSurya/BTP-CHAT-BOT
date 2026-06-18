"""SAP HANA Cloud access layer.

Responsibilities:
  * Manage connections with a small, thread-safe pool and automatic reconnect.
  * Introspect the live schema (tables, views, columns, primary/foreign keys)
    at startup and cache it, with an explicit refresh.
  * Execute read-only queries with a row cap and JSON-safe value coercion.

Nothing here connects at import time, so the app can start even if the
database is briefly unavailable; connections happen on first use.
"""
import datetime
import json
import logging
import threading
from contextlib import contextmanager
from decimal import Decimal

from hdbcli import dbapi

from prompts.table_knowledge import TABLE_BUSINESS_CONTEXT

from .sql_guard import RESTRICTED_TABLES

log = logging.getLogger("procura.hana")

# Column types we skip when sampling, to avoid pulling large binary/text blobs.
_LOB_TYPES = {
    "BLOB", "CLOB", "NCLOB", "TEXT", "BINTEXT",
    "ST_GEOMETRY", "ST_POINT", "ST_GEOMETRYCOLLECTION",
}


def _truncate(value, maxlen: int):
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if len(text) <= maxlen:
        return text
    return text[: maxlen - 1] + "\u2026"


def _coerce(row):
    """Convert a row of HANA values into JSON-serialisable Python values."""
    out = []
    for value in row:
        if isinstance(value, Decimal):
            out.append(float(value))
        elif isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            out.append(value.isoformat())
        elif isinstance(value, (bytes, bytearray, memoryview)):
            out.append(bytes(value).hex())
        else:
            out.append(value)
    return out


def _is_connection_error(error) -> bool:
    text = str(error).lower()
    keywords = (
        "connection", "closed", "broken", "timeout", "network",
        "reset", "not connected", "-10709", "-10807",
    )
    return any(k in text for k in keywords)


class HanaService:
    def __init__(self, config):
        self.cfg = config
        self._pool = []
        self._lock = threading.Lock()
        self._schema_cache = None

    # --- connection management -------------------------------------------
    def _new_connection(self):
        log.info("Opening a new HANA connection to %s", self.cfg.HANA_ADDRESS)
        return dbapi.connect(
            address=self.cfg.HANA_ADDRESS,
            port=self.cfg.HANA_PORT,
            user=self.cfg.HANA_USER,
            password=self.cfg.HANA_PASSWORD,
            encrypt=self.cfg.HANA_ENCRYPT,
            sslValidateCertificate=self.cfg.HANA_SSL_VALIDATE,
            connectTimeout=15000,
        )

    def _acquire(self):
        with self._lock:
            while self._pool:
                conn = self._pool.pop()
                try:
                    if conn.isconnected():
                        return conn
                except Exception:
                    pass
                self._safe_close(conn)
        return self._new_connection()

    def _release(self, conn):
        with self._lock:
            if len(self._pool) < self.cfg.POOL_SIZE:
                self._pool.append(conn)
                return
        self._safe_close(conn)

    @staticmethod
    def _safe_close(conn):
        try:
            conn.close()
        except Exception:
            pass

    @contextmanager
    def _connection(self):
        conn = self._acquire()
        try:
            yield conn
        except dbapi.Error:
            self._safe_close(conn)
            raise
        else:
            self._release(conn)

    # --- query execution --------------------------------------------------
    def qualify_sql(self, sql: str) -> str:
        """Automatically qualify un-qualified ZHANADB_* tables with the current schema."""
        if not sql:
            return sql
        schema = self.cfg.HANA_SCHEMA
        if not schema:
            try:
                with self._connection() as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute("SELECT CURRENT_SCHEMA FROM DUMMY")
                        row = cursor.fetchone()
                        if row:
                            schema = row[0]
                    finally:
                        cursor.close()
            except Exception:
                pass
        if not schema:
            schema = "CURRENT_SCHEMA"
        import re
        return re.sub(r'(?<!\.)"ZHANADB_([A-Za-z0-9_]+)"', f'"{schema}"."ZHANADB_\\1"', sql)

    def execute_query(self, sql: str, max_rows: int = None) -> dict:
        """Run a read-only query and return {columns, rows, truncated}.
        Retries once on a transient connection error."""
        sql = self.qualify_sql(sql)
        max_rows = max_rows or self.cfg.MAX_RESULT_ROWS
        last_error = None
        for attempt in range(2):
            try:
                with self._connection() as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute(sql)
                        columns = (
                            [d[0] for d in cursor.description]
                            if cursor.description
                            else []
                        )
                        rows = cursor.fetchmany(max_rows)
                        truncated = (
                            len(rows) >= max_rows and cursor.fetchone() is not None
                        )
                        data = [dict(zip(columns, _coerce(r))) for r in rows]
                        return {
                            "columns": columns,
                            "rows": data,
                            "truncated": truncated,
                        }
                    finally:
                        cursor.close()
            except dbapi.Error as error:
                last_error = error
                if attempt == 0 and _is_connection_error(error):
                    log.warning("Transient HANA error, retrying once: %s", error)
                    continue
                raise
        raise last_error

    # --- user identity (ZHANADB_USERSET) ----------------------------------
    def fetch_user(self, user_id: str) -> dict | None:
        """Look up a single user by ID from ZHANADB_USERSET.

        Uses a parameterised query to prevent SQL injection.  Returns a
        dict of column-name -> value for the matched row, or None if the
        user is not found.  The table is queried directly with the schema
        discovered at introspection time (or CURRENT_SCHEMA).
        """
        if not user_id:
            return None
        schema = self.cfg.HANA_SCHEMA
        try:
            with self._connection() as conn:
                cursor = conn.cursor()
                try:
                    if not schema:
                        cursor.execute("SELECT CURRENT_SCHEMA FROM DUMMY")
                        schema = cursor.fetchone()[0]
                    # Discover columns dynamically so we don't hardcode field names.
                    cursor.execute(
                        "SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS "
                        "WHERE SCHEMA_NAME = ? AND TABLE_NAME = 'ZHANADB_USERSET' "
                        "ORDER BY POSITION",
                        (schema,),
                    )
                    columns = [row[0] for row in cursor.fetchall()]
                    if not columns:
                        log.warning("ZHANADB_USERSET table not found in schema %s", schema)
                        return None

                    col_list = ", ".join('"' + c + '"' for c in columns)
                    # Try common ID column names: USERID, USER_ID, ID, EMAIL.
                    id_column = None
                    for candidate in ("USERID", "USER_ID", "ID", "LOGINNAME", "LOGIN_NAME", "EMAIL", "USERNAME", "USER_NAME"):
                        if candidate in columns:
                            id_column = candidate
                            break
                    if id_column is None:
                        # Fall back to the first column if none of the common names match.
                        id_column = columns[5]

                    sql = (
                        f'SELECT {col_list} FROM "{schema}"."ZHANADB_USERSET" '
                        f'WHERE "{id_column}" = ? LIMIT 1'
                    )
                    cursor.execute(sql, (user_id,))
                    row = cursor.fetchone()
                    if not row:
                        return None
                    return dict(zip(columns, _coerce(row)))
                finally:
                    cursor.close()
        except Exception:
            log.exception("Failed to fetch user %s from ZHANADB_USERSET", user_id)
            return None

    # --- schema introspection --------------------------------------------
    def introspect_schema(self, refresh: bool = False) -> dict:
        if self._schema_cache is not None and not refresh:
            return self._schema_cache

        with self._connection() as conn:
            cursor = conn.cursor()
            try:
                schema = self.cfg.HANA_SCHEMA
                if not schema:
                    cursor.execute("SELECT CURRENT_SCHEMA FROM DUMMY")
                    schema = cursor.fetchone()[0]

                tables = {}

                # Base tables.
                cursor.execute(
                    """
                        SELECT
                            TABLE_NAME,
                            COLUMN_NAME,
                            DATA_TYPE_NAME,
                            IS_NULLABLE
                        FROM SYS.TABLE_COLUMNS
                        WHERE SCHEMA_NAME = ?
                        AND TABLE_NAME IN ( 'ZHANADB_CHANGENOTERECOSET',
                                            'ZHANADB_CHANGENOTESET',
                                            'ZHANADB_CNAPPROVALSTAGEMASTERSET',
                                            'ZHANADB_CNAPPROVALTEMPLATESET',
                                            'ZHANADB_CNPOLIMITMASTERSET',
                                            'ZHANADB_CNWF1STAGESET',
                                            'ZHANADB_COMMENTSET',
                                            'ZHANADB_COMMENTSETRECOBY',
                                            'ZHANADB_CONFIGURATION',
                                            'ZHANADB_DOCUMENTMASTERSET',
                                            'ZHANADB_DOCUMENTSET',
                                            'ZHANADB_INSPECTIONITEMSET',
                                            'ZHANADB_INSPECTIONSET',
                                            'ZHANADB_MATERIALFAMILYSET',
                                            'ZHANADB_MATERIALSET',
                                            'ZHANADB_MDCCRELATIONSET',
                                            'ZHANADB_MPLMAILCONFIGURATION',
                                            'ZHANADB_NCRDCRDATASET',
                                            'ZHANADB_NCRDCRITEMDATASET',
                                            'ZHANADB_NCRDCRRECOSET',
                                            'ZHANADB_POASSIGNMENTSET',
                                            'ZHANADB_POBGRELATIONSET',
                                            'ZHANADB_PROJECTWBSSET',
                                            'ZHANADB_PURCHASEORDERSET',
                                            'ZHANADB_QUERYLISTCONCERNEDSET',
                                            'ZHANADB_QUERYLISTITEMSET',
                                            'ZHANADB_QUERYLISTRECOSET',
                                            'ZHANADB_QUERYLISTSET',
                                            'ZHANADB_SERVICEORDERDEDUCTIONSET',
                                            'ZHANADB_SERVICEORDERRECOMENDERSET',
                                            'ZHANADB_SERVICEORDERSET',
                                            'ZHANADB_TPIRELATIONSET',
                                            'ZHANADB_USERROLESET',
                                            'ZHANADB_USERSET',
                                            'ZHANADB_WBS',
                                            'ZHANADB_WBSAPPROVEDBY',
                                            'ZHANADB_WBSTRAINSET')
                        ORDER BY TABLE_NAME, POSITION;
                    """,
                    (schema,),
                )
                for tname, cname, dtype, nullable in cursor.fetchall():
                    if tname in RESTRICTED_TABLES:
                        continue
                    tables.setdefault(tname, {"kind": "table", "columns": []})
                    tables[tname]["columns"].append(
                        {"name": cname, "type": dtype, "nullable": nullable == "TRUE"}
                    )

                # Views (CAP often exposes data through views).
                cursor.execute(
                    """
                    SELECT VIEW_NAME, COLUMN_NAME, DATA_TYPE_NAME, IS_NULLABLE
                    FROM SYS.VIEW_COLUMNS
                    WHERE SCHEMA_NAME = ?
                    ORDER BY VIEW_NAME, POSITION
                    """,
                    (schema,),
                )
                from prompts.table_knowledge import TABLE_BUSINESS_CONTEXT
                for vname, cname, dtype, nullable in cursor.fetchall():
                    if vname in RESTRICTED_TABLES:
                        continue
                    # Only keep views starting with ZHANADB_ or explicitly mapped in glossary
                    if not vname.upper().startswith("ZHANADB_") and vname not in TABLE_BUSINESS_CONTEXT:
                        continue
                    tables.setdefault(vname, {"kind": "view", "columns": []})
                    tables[vname]["columns"].append(
                        {"name": cname, "type": dtype, "nullable": nullable == "TRUE"}
                    )

                # Foreign keys help the model write correct JOINs.
                relationships = []
                try:
                    cursor.execute(
                        """
                        SELECT TABLE_NAME, COLUMN_NAME,
                               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                        FROM SYS.REFERENTIAL_CONSTRAINTS
                        WHERE SCHEMA_NAME = ?
                        """,
                        (schema,),
                    )
                    for src_t, src_c, ref_t, ref_c in cursor.fetchall():
                        if src_t in RESTRICTED_TABLES or ref_t in RESTRICTED_TABLES:
                            continue
                        relationships.append(
                            {
                                "from_table": src_t,
                                "from_column": src_c,
                                "to_table": ref_t,
                                "to_column": ref_c,
                            }
                        )
                except dbapi.Error as fk_error:
                    log.info("Foreign-key introspection skipped: %s", fk_error)

                # Sample a few real rows per object so the model understands
                # what each table actually contains (real columns and values),
                # not just column names. Bounded and cached.
                sample_n = self.cfg.SAMPLE_ROWS
                if sample_n > 0:
                    maxlen = self.cfg.SAMPLE_VALUE_MAXLEN
                    for tname, tinfo in tables.items():
                        non_lob = [
                            c["name"]
                            for c in tinfo["columns"]
                            if c["type"].upper() not in _LOB_TYPES
                        ]
                        tinfo["sample"] = []
                        if not non_lob:
                            continue
                        col_list = ", ".join(f'"{c}"' for c in non_lob)
                        sample_sql = (
                            f'SELECT {col_list} FROM "{schema}"."{tname}" '
                            f"LIMIT {sample_n}"
                        )
                        try:
                            cursor.execute(sample_sql)
                            cols = (
                                [d[0] for d in cursor.description]
                                if cursor.description
                                else []
                            )
                            for raw in cursor.fetchall():
                                coerced = _coerce(raw)
                                tinfo["sample"].append(
                                    {
                                        c: _truncate(v, maxlen)
                                        for c, v in zip(cols, coerced)
                                    }
                                )
                        except dbapi.Error as sample_error:
                            log.info(
                                "Sample fetch skipped for %s: %s", tname, sample_error
                            )

                self._schema_cache = {
                    "schema": schema,
                    "tables": tables,
                    "relationships": relationships,
                }
                log.info(
                    "Schema introspected: %d objects in schema %s",
                    len(tables),
                    schema,
                )
                return self._schema_cache
            finally:
                cursor.close()

    def schema_prompt(self, refresh: bool = False) -> str:
        """Render the schema as a compact, fully-quoted description for the LLM.

        Identifiers are presented with the exact double quotes HANA needs,
        because CAP-generated objects are usually case-sensitive.
        """
        meta = self.introspect_schema(refresh=refresh)
        schema = meta["schema"]
        table_names = list(meta["tables"].keys())
        lines = [
            f'Database schema (HANA schema name: "{schema}").',
            "Reference every object as \"SCHEMA\".\"TABLE\".\"COLUMN\" using these "
            "exact quoted names. Tables and columns are case-sensitive.",
            "Lines beginning with \"e.g.\" are REAL sample rows from that table — "
            "use them to understand what each table actually holds. Only the "
            "columns listed exist; there are no other columns.",
            "",
            "EXACT TABLE/VIEW NAMES (the complete, authoritative list — this schema "
            "has no other objects). Whenever a field requires a table name "
            "(overview_table, or any table in SQL), you MUST copy one of these "
            "strings EXACTLY, character-for-character, including the ZHANADB_ "
            "prefix and the exact casing. NEVER use a name mentioned in a "
            "\"Purpose\" or \"Connected Tables\" note below — those are plain-English "
            "business descriptions, not real identifiers, and copying them WILL fail:",
            ", ".join(table_names),
            "",
        ]
        for name, info in meta["tables"].items():
            cols = ", ".join(
                f'"{c["name"]}" {c["type"]}' for c in info["columns"]
            )
            tag = "VIEW" if info["kind"] == "view" else "TABLE"
            lines.append(f'{tag} "{schema}"."{name}" ({cols})')
            context = TABLE_BUSINESS_CONTEXT.get(name)
            if context:
                lines.append(f'    Purpose: {context["purpose"]}')
                if context.get("connected_tables"):
                    lines.append(
                        "    Connected Tables (business names, NOT real identifiers — "
                        f'never use these literally): {", ".join(context["connected_tables"])}'
                    )
                if context.get("importance"):
                    lines.append(f'    Importance: {context["importance"]}')
            for row in info.get("sample") or []:
                line = "    e.g. " + json.dumps(row, ensure_ascii=False, default=str)
                if len(line) > 500:
                    line = line[:499] + "\u2026"
                lines.append(line)

        if meta["relationships"]:
            lines.append("")
            lines.append("Relationships (foreign keys) you can JOIN on:")
            for rel in meta["relationships"]:
                lines.append(
                    f'  "{schema}"."{rel["from_table"]}"."{rel["from_column"]}" '
                    f'-> "{schema}"."{rel["to_table"]}"."{rel["to_column"]}"'
                )
        return "\n".join(lines)

    def schema_summary(self, refresh: bool = False) -> str:
        """A slim list of what information exists, for grounding suggestions.

        One line per object with plain column names (no types, quotes, or
        samples). Used by the analyst to suggest relevant alternatives in
        natural language when a request returns nothing.
        """
        meta = self.introspect_schema(refresh=refresh)
        lines = ["AVAILABLE INFORMATION (for suggesting relevant alternatives):"]
        for name, info in meta["tables"].items():
            cols = ", ".join(c["name"] for c in info["columns"])
            context = TABLE_BUSINESS_CONTEXT.get(name)
            purpose = f' -- {context["purpose"]}' if context else ""
            lines.append(f"- {name}: {cols}{purpose}")
        return "\n".join(lines)
