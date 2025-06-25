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



def test_r2m_office_db():
    # ─── Configuration ────────────────────────────────────────────────────────
    object_pairs = [
        (98, 99),
        (104, 78),
        (1,  88),
        (56, 98),
        (98, 56),
        (82, 83),
        (8, 104),
        (1, 52),
        (5, 52),
        (97, 102)
    ]
    camera_id    = 1      # for front/behind/left/right
    scale_factor = 10.0   # for above, below, on_top, etc.

    queries = {
        "above":  "above.sql",
        "below":  "below.sql",
        "front":  "front.sql",
        "behind": "behind.sql",
        "left":   "left.sql",
        "right":  "right.sql",
    }

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        # Load all SQL texts
        sql_texts = {name: load_query(fn) for name, fn in queries.items()}

        # 1) Camera info
        with conn.cursor() as cur:
            cur.execute("SELECT id, position, fov FROM camera WHERE id = %s", (camera_id,))
            cam_id, cam_pos, cam_fov = cur.fetchone()
        print(f"Camera ID={cam_id}, position={cam_pos}, fov={cam_fov}")

        # 2) Build name map
        all_ids = {oid for pair in object_pairs for oid in pair}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM room_objects WHERE id = ANY(%s)",
                (list(all_ids),)
            )
            name_map = {row[0]: row[1] for row in cur.fetchall()}

        # 3) Test each pair
        for x_id, y_id in object_pairs:
            x_name = name_map.get(x_id, f"ID {x_id}")
            y_name = name_map.get(y_id, f"ID {y_id}")

            print(f"\nObjects: {x_name} (ID {x_id}) → {y_name} (ID {y_id})")

            # Camera‐dependent relations
            for rel in ("front", "behind", "left", "right"):
                sql = sql_texts[rel]
                # note: these expect args (object_y_id, object_x_id, camera_id, s)
                row = run_query(conn, sql, (y_id, x_id, camera_id, scale_factor))[0]
                flag = row[3]
                status = "is" if flag else "is NOT"
                print(f"  [{rel.title():>6}] {x_name} {status} {rel} of {y_name}")

            # Camera‐independent: above & below
            above_row = run_query(conn, sql_texts["above"], (x_id, y_id,camera_id, scale_factor))[0]
            above_flag = above_row[3]
            below_row = run_query(conn, sql_texts["below"], (x_id, y_id,camera_id, scale_factor))[0]
            below_flag = below_row[3]

            print(f"  [Above ] {x_name} is{' ' if above_flag else ' NOT '}above {y_name}")
            print(f"  [Below ] {x_name} is{' ' if below_flag else ' NOT '}below {y_name}")

            # Composed relations
            print("  [On Top]   composed on_top_relation:")
            for line in on_top_relation(x_id, y_id, camera_id, scale_factor).splitlines():
                print("    " + line)

            print("  [Leans On] composed leans_on_relation:")
            for line in leans_on_relation(x_id, y_id, camera_id, scale_factor).splitlines():
                print("    " + line)

            print("  [Affixed]  composed affixed_to_relation:")
            for line in affixed_to_relation(x_id, y_id, camera_id, scale_factor).splitlines():
                print("    " + line)

    finally:
        conn.close()