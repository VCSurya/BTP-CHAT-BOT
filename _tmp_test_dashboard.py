from services.dashboard_service import build_dashboard, build_table_overview, DashboardError


class FakeHana:
    def __init__(self):
        self.schema = {
            "schema": "MYSCHEMA",
            "tables": {
                "MATERIALS": {
                    "kind": "table",
                    "columns": [
                        {"name": "MATERIALID", "type": "VARCHAR", "nullable": False},
                        {"name": "MATERIALFAMILY", "type": "VARCHAR", "nullable": True},
                        {"name": "MATERIALSUBFAMILY", "type": "VARCHAR", "nullable": True},
                    ],
                },
            },
        }
        self.data = {
            "STRUCTURAL": 27, "REBAR": 11, "HOLLOW SECTION": 17,
            "ANCHOR BOLT": 1, "CABLE": 1, "FITTING": 1, "PIPE": 1,
        }

    def introspect_schema(self, refresh=False):
        return self.schema

    def execute_query(self, sql, max_rows=None):
        if 'COUNT(*) AS "TOTAL"' in sql:
            return {"columns": ["TOTAL"], "rows": [{"TOTAL": sum(self.data.values())}]}
        ranked = sorted(self.data.items(), key=lambda kv: kv[1], reverse=True)[:max_rows]
        return {"columns": ["LABEL", "COUNT"], "rows": [{"LABEL": k, "COUNT": v} for k, v in ranked]}


hana = FakeHana()
overview = build_table_overview(hana, "MATERIALS", max_cols=2, top_n=8)
print("total_records:", overview["total_records"])
for c in overview["charts"]:
    print(" chart:", c["title"], c["labels"], c["datasets"])

full = build_dashboard(hana, max_tables=6, max_cols_per_table=2, top_n=8)
print("sections:", len(full["sections"]))

try:
    build_table_overview(hana, "NOPE")
except DashboardError as e:
    print("expected error:", e)
