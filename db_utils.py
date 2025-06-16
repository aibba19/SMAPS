# db_utils.py
import os
import psycopg2
from pathlib import Path
from typing import Tuple, Any
from config import DB_CONFIG
import importlib.util
import sys
from pathlib import Path
from typing import Any, Tuple



# ---------------------------------------------------------------------------
# Original helpers (unchanged)
# ---------------------------------------------------------------------------
def get_connection():
    try:
        return psycopg2.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            dbname=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )
    except Exception as e:
        print("Error connecting to database:", e)
        raise


def load_query(filename_or_path):
    if isinstance(filename_or_path, Path):
        path = filename_or_path
    else:
        path = Path(__file__).with_suffix("").parent / "sql" / filename_or_path
    text = path.read_text(encoding="utf-8")
    return text.lstrip("\ufeff")     # strip BOM


def run_query(conn, query: str, params: Tuple[Any, ...] = None):
    with conn.cursor() as cur:
        try:
            cur.execute(query, params)
            return cur.fetchall()
        except Exception as e:
            conn.rollback()
            print("Error executing query:", e)
            raise


# ---------------------------------------------------------------------------
# Simplified SQL‑file loader
# ---------------------------------------------------------------------------
SQL_DIR = Path(__file__).with_suffix("").parent / "sql"

# ---------------------------------------------------------------------------
# Composed‑relation Python functions
# ---------------------------------------------------------------------------
def _import_composed_funcs():
    """
    Load SQL/composed_queries.py regardless of package layout and
    return its three relation functions.
    """
    try:
        # Preferred: sql is a package:  from sql.composed_queries import ...
        from sql.composed_queries import (
            on_top_relation,
            leans_on_relation,
            affixed_to_relation,
        )
    except ImportError:
        # Fallback: load the file directly
        comp_path = "sql/composed_queries.py"
        spec = importlib.util.spec_from_file_location("composed_queries", comp_path)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)                 # type: ignore[union-attr]
        on_top_relation = module.on_top_relation        # type: ignore[attr-defined]
        leans_on_relation = module.leans_on_relation    # type: ignore[attr-defined]
        affixed_to_relation = module.affixed_to_relation

    return {
        "on_top_of": on_top_relation,
        "leans_on": leans_on_relation,
        "affixed_to": affixed_to_relation,
    }


COMPOSED_FUNCS = _import_composed_funcs()

def load_query(file_or_path: str | Path) -> str:
    """
    Return the text of a .sql file.

    Accepts either the bare filename (e.g. 'above.sql') or an absolute/relative
    Path object.  Always resolves against the ./sql directory first.
    """
    path = Path(file_or_path)
    if not path.suffix:                 # maybe they passed "above" w/o .sql
        path = path.with_suffix(".sql")

    if not path.is_absolute():
        path = SQL_DIR / path.name      # resolve relative to ./sql

    text = path.read_text(encoding="utf-8")
    return text.lstrip("\ufeff")        # strip UTF‑8 BOM if present


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
def _template_query(conn, template_file: str | Path, params: Tuple[Any, ...]):
    sql_text = load_query(template_file)
    return run_query(conn, sql_text, params)


def run_template_query4(conn, tpl, x, y, camera, s):
    return _template_query(conn, tpl, (x, y, camera, s))


def run_template_query3(conn, tpl, id1, id2, thresh):
    return _template_query(conn, tpl, (id1, id2, thresh))


def run_template_query2(conn, tpl, id1, id2):
    return _template_query(conn, tpl, (id1, id2))


# ---------------------------------------------------------------------------
# Master executor (unchanged interface – simpler load_query usage)
# ---------------------------------------------------------------------------
def run_spatial_call(
    conn,
    call: dict,
    template_paths: dict,
    camera_default: int = 1,
    s_default: int = 1,
):
    """
    Execute a single call from plan_spatial_queries(), now using a_id/b_id.
    """

    # Skip if requires camera but none available
    if (
        call.get("type") == "template"
        and call.get("requires_camera")
        and not call.get("camera_available", False)
    ):
        return {
            "call": call,
            "status": "skipped",
            "rows": [],
            "reason": "camera unavailable",
        }

    try:
        if call["type"] == "template":
            tpl_key = call["template"]

            # 4-param directionals
            if tpl_key in {"above", "below", "front", "behind", "left", "right"}:
                rows = run_template_query4(
                    conn,
                    template_paths[tpl_key],
                    call["b_id"],                   # x_id (tested)
                    call["a_id"],                   # y_id (reference)
                    call.get("camera_id", camera_default),
                    call.get("s", s_default),
                )

            # 3-param near/far
            elif tpl_key in {"near", "far"}:
                rows = run_template_query3(
                    conn,
                    template_paths[tpl_key],
                    call["a_id"],                   # id1
                    call["b_id"],                   # id2
                    call.get("s", s_default),
                )

            # 2-param touches
            elif tpl_key == "touches":
                rows = run_template_query2(
                    conn,
                    template_paths[tpl_key],
                    call["a_id"],
                    call["b_id"],
                )

            # composed Python relations
            elif tpl_key in COMPOSED_FUNCS:
                _import_composed_funcs()
                func = COMPOSED_FUNCS[tpl_key]
                result = func(
                    call["a_id"],
                    call["b_id"],
                    call.get("camera_id", camera_default),
                    call.get("s", s_default),
                )
                rows = [result]

            else:
                return {
                    "call": call,
                    "status": "skipped",
                    "rows": [],
                    "reason": f"unknown template '{tpl_key}'",
                }

            return {"call": call, "status": "executed", "rows": rows, "reason": None}

        # custom SQL
        elif call["type"] == "sql":
            rows = run_query(conn, call["sql"])
            return {"call": call, "status": "executed", "rows": rows, "reason": None}

        else:
            return {
                "call": call,
                "status": "skipped",
                "rows": [],
                "reason": f"unknown call type '{call.get('type')}'",
            }

    except Exception as exc:
        conn.rollback()
        return {"call": call, "status": "skipped", "rows": [], "reason": str(exc)}
