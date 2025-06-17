import json
import logging
import os
import re
import psycopg2 
from psycopg2 import sql
from config import DB_CONFIG
from config import MY_OPENAI_KEY
from sql.composed_queries import *
from db_utils import *
import json
import openai

from prompts.spatial_planner2 import spatial_planner
from prompts.entity_extraction2 import extract_entities
from prompts.decompose_rule import decompose_rule
from prompts.evaluate_rule import evaluate_rule

from pathlib import Path
from typing import List, Tuple, Optional, Dict

# ──────────────────────────────────────────────────────────────────────────
# 0.  Template catalogue  (key → SQL filename or None for composed funcs)
# ──────────────────────────────────────────────────────────────────────────
TEMPLATE_MAP: Dict[str, str | None] = {
    # 4‑param directionals
    "above": "above.sql",
    "below": "below.sql",
    "front": "front.sql",
    "behind": "behind.sql",
    "left": "left.sql",
    "right": "right.sql",
    # 3‑param distance
    "near": "near_far.sql",
    "far": "near_far.sql",
    # 2‑param boolean
    "touches": "touches.sql",
    # composed (executed in Python, no SQL file needed)
    "on_top_of": None,
    "leans_on": None,
    "affixed_to": None,
}

# Turn every SQL filename into a Path for db_utils
TEMPLATE_PATHS = {
    k: (Path(__file__).with_suffix("").parent / "sql" / v) if v else None
    for k, v in TEMPLATE_MAP.items()
}

TEMPLATE_CATALOGUE = {
    "touches": "True when two object bounding boxes are ≤ 0.1 m apart or intersect.",
    "front": "True when A is in front of B, within a small distance threshold.",
    "behind": "True when A is behind B, relative to the camera point of view, within a small threshold.",
    "left": "True when A is to the left of B, within a small distance threshold.",
    "right": "True when A is to the right of B, within a small distance threshold.",
    "above": "True when A is above B, within a small distance threshold.",
    "below": "True when A is below B, within a small distance threshold.",
    "on_top_of": "True when A is placed directly on top of B.",
    "leans_on": "True when A is supported by B.",
    "affixed_to": "True when A is affixed to B.",
    "near": "True when the distance between A and B is less than a defined threshold.",
    "far": "True when the distance between A and B is greater than a defined threshold."
}

# ──────────────────────────────────────────────────────────────────────────
# 1.  Define the H&S checks you want to run
# ──────────────────────────────────────────────────────────────────────────
CHECKS = {
    "extinguisher_check2": (
        "Are all portable fire extinguishers readily accessible and not restricted by stored items?"
        #"Have combustible materials been stored away from sources of ignition?"
        #"Are portable fire extinguishers either securely wall mounted or on a supplied stand?"
    ),
}


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

def fetch_types_and_names(
    table_name: str = "room_objects",
    id_column: str = "id",
    type_column: str = "ifc_type",
    name_column: str = "name",
    *,
    outfile: Optional[Path | str] = "ifc_types_names.txt",  # set to None to skip writing
    file_mode: str = "w",                                   # or "a" to append
    line_template: str = "{id}  -  {type}  -  {name}\n"     # customise if you like
) -> List[Tuple[int, str, str]]:
    """
    Fetch (id, type, name) tuples from the given table/columns.

    • Prints each tuple.
    • Optionally writes them to *outfile* (text file).
    • Returns the list of tuples [(id, type, name), …].

    Parameters
    ----------
    id_column : str
        Name of the ID column to fetch.
    outfile : str | Path | None
        Where to write the data. Pass None to disable file output.
    file_mode : str
        'w' = overwrite (default), 'a' = append, etc.
    line_template : str
        Format string for each line; supports {id}, {type}, {name}.
    """
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            query = sql.SQL("SELECT {id_col}, {type_col}, {name_col} FROM {tbl}").format(
                id_col=sql.Identifier(id_column),
                type_col=sql.Identifier(type_column),
                name_col=sql.Identifier(name_column),
                tbl=sql.Identifier(table_name)
            )
            cur.execute(query)
            rows = cur.fetchall()  # List of (id, type, name)

        # Prepare file output if requested
        writer = None
        if outfile is not None:
            outfile = Path(outfile)
            outfile.parent.mkdir(parents=True, exist_ok=True)
            writer = outfile.open(file_mode, encoding="utf-8")

        # Print and write each row
        for obj_id, obj_type, obj_name in rows:
            line = line_template.format(id=obj_id, type=obj_type, name=obj_name)
            print(line.rstrip())
            if writer:
                writer.write(line)

        if writer:
            writer.close()

        return rows

    finally:
        conn.close()

def load_objects_and_maps() -> Tuple[List[Tuple[int, str, str]], Dict[int, Tuple[str, str]], List[int], Dict[str, List[int]]]:
    """
    Load all objects from the PostgreSQL DB and build helpful lookup maps.

    Returns
    -------
    all_objects : List of (id, ifc_type, name) tuples
    id_to_obj    : Dict mapping ID → (ifc_type, name)
    all_ids      : List of all object IDs
    type_to_ids  : Dict mapping ifc_type → list of IDs
    """
    print("DEBUG: Fetching all objects (id, type, name) from DB...")
    all_objects = fetch_types_and_names()
    print(f"DEBUG: Retrieved {len(all_objects)} objects.\n")

    # Build id_to_obj mapping: ID → (ifc_type, name)
    id_to_obj: Dict[int, Tuple[str, str]] = {
        obj_id: (ifc_type, name) for obj_id, ifc_type, name in all_objects
    }
    all_ids = list(id_to_obj.keys())

    # Build type_to_ids mapping: ifc_type → [IDs]
    type_to_ids: Dict[str, List[int]] = {}
    for obj_id, ifc_type, _ in all_objects:
        type_to_ids.setdefault(ifc_type, []).append(obj_id)

    print("DEBUG: Built ID→object and type→IDs maps.\n")
    return all_objects, id_to_obj, all_ids, type_to_ids

def prepare_template_paths() -> Dict[str, Path]:
    """
    Prepare and return a dictionary mapping template names to their SQL file paths.
    """
    SQL_DIR = Path(__file__).parent / "sql"
    print(f"DEBUG: SQL directory is {SQL_DIR}")
    template_paths: Dict[str, Path] = {
        name: (SQL_DIR / fname) for name, fname in TEMPLATE_MAP.items() if fname
    }
    print(f"DEBUG: Prepared template paths for {len(template_paths)} SQL files.\n")
    return template_paths

def execute_spatial_calls(
    plan: Dict,
    id_to_obj: Dict[int, Tuple[str, str]],
    type_to_ids: Dict[str, List[int]],
    all_ids: List[int],
    conn,
    template_paths: Dict[str, Path],
    log_file
) -> List[Dict]:
    """
    Execute spatial calls (SQL templates) for each entry in the plan, logging and collecting positive relations.

    Parameters
    ----------
    plan            : The "plans" dict returned by spatial_planner()
    id_to_obj       : ID→(ifc_type, name) map
    type_to_ids     : ifc_type→[IDs] map
    all_ids         : List of all object IDs
    conn            : Active psycopg2 connection
    template_paths  : Template name → file path map
    log_file        : Open file handle for logging
    """
    print("DEBUG: Executing spatial calls for each planned relation...")
    positive_relations: List[Dict] = []

    # Iterate through each planned check entry
    for entry in plan.get("plans", []):
        idx = entry["check_index"]
        relation_text = entry.get("relation_text", "")
        templates_list = [t["template"] for t in entry["templates"]]

        for tmpl in entry["templates"]:
            tpl_name = tmpl["template"]
            a_src, b_src = tmpl["a_source"], tmpl["b_source"]

            # Determine the list of 'a' IDs (reference)
            if a_src == "reference_ids":
                a_ids = entry["reference"]["reference_ids"]
            elif a_src == "reference_ifc_types":
                a_ids = [
                    oid
                    for t in entry["reference"].get("reference_ifc_types", [])
                    for oid in type_to_ids.get(t, [])
                ]
            else:  # any_nearby
                a_ids = entry["reference"]["reference_ids"]

            # Determine the list of 'b' IDs (against)
            if b_src == "against_ids":
                b_ids = entry["against"]["against_ids"]
            elif b_src == "against_ifc_types":
                b_ids = [
                    oid
                    for t in entry["against"].get("against_ifc_types", [])
                    for oid in type_to_ids.get(t, [])
                ]
            else:  # any_nearby
                b_ids = all_ids

            # Run the spatial function 1-to-1 for each pair of a_id and b_id
            for a_id in a_ids:
                a_type, a_name = id_to_obj[a_id]
                for b_id in b_ids:
                    if a_id == b_id:
                        continue  # skip self-comparisons
                    b_type, b_name = id_to_obj[b_id]

                    call = {
                        "type":     "template",
                        "template": tpl_name,
                        "a_id":     b_id,
                        "b_id":     a_id
                    }

                    # --- Log the call request ---
                    log_file.write("=== SPATIAL CALL ===\n")
                    log_file.write(json.dumps(call, ensure_ascii=False) + "\n")

                    # Execute the SQL template via run_spatial_call
                    result = run_spatial_call(conn, call, template_paths)

                    # --- Log the result ---
                    log_file.write("RESULT:\n")
                    log_file.write(json.dumps(result, ensure_ascii=False) + "\n\n")
                    log_file.flush()

                    # Determine if relation held based on result rows
                    held = False
                    relation_value = ""
                    rows = result.get("rows", [])
                    if rows:
                        first = rows[0]
                        if tpl_name == "touches":
                            held = bool(first[0])
                            relation_value = first[1]
                        elif tpl_name in {"front", "left", "right", "behind", "above", "below"}:
                            held = bool(first[3])
                            relation_value = first[4] if held else None
                        elif tpl_name in {"near", "far"}:
                            # near_far.sql returns [relation, distance, is_near, is_far]
                            relation_text = first[0]
                            is_near_flag = first[2]
                            is_far_flag = first[3]
                            if tpl_name == "near":
                                held = bool(is_near_flag)
                            else:
                                held = bool(is_far_flag)
                            relation_value = relation_text if held else None
                        elif tpl_name in {"affixed_to", "leans_on", "on_top_of"}:
                            held = bool(first[0])
                            relation_value = first[1]

                    # If relation holds, record it
                    if held:
                        positive_relations.append({
                            "check_index":     idx,
                            "template":        tpl_name,
                            "a_id":            a_id,
                            "a_name":          a_name,
                            "a_type":          a_type,
                            "b_id":            b_id,
                            "b_name":          b_name,
                            "b_type":          b_type,
                            "relation_value":  relation_value
                        })

    print(f"DEBUG: Found {len(positive_relations)} positive relations.\n")
    return positive_relations


def build_summaries(
    plan: Dict,
    positive_relations: List[Dict],
    id_to_obj: Dict[int, Tuple[str, str]]
) -> List[str]:
    """
    Build human‐readable summaries for each reference entry based on positive relations.

    Parameters
    ----------
    plan                : The plan dict returned by spatial_planner()
    positive_relations  : List of dicts describing each held relation
    id_to_obj           : ID→(ifc_type, name) map

    Returns
    -------
    summaries : List of strings, each summarizing one reference check
    """
    print("DEBUG: Building human‐readable summaries for each check entry...")
    summaries: List[str] = []

    # Mapping from template name to a phrase for readability
    relation_phrases = {
        "touches": "touches",
        "front":   "are in front of",
        "right":   "are to the right of",
        "left":    "are to the left of",
        "behind":  "are behind",
        "above":   "are above",
        "below":   "are below",
        "near":    "are near",
        "far":     "are far from",
    }

    for entry in plan.get("plans", []):
        idx = entry["check_index"]
        relation_text = entry.get("relation_text", "")
        templates_list = [t["template"] for t in entry["templates"]]

        # Describe the "against" clause
        against = entry["against"]
        if against["type"] == "any":
            against_desc = "all objects in the DB"
        elif against["type"] == "category":
            types = ", ".join(against["against_ifc_types"])
            against_desc = f"objects of IFC types: {types}"
        else:
            against_desc = f"specific objects matching '{against['value']}'"

        # Determine reference items and labels
        if entry["reference"]["type"] == "object":
            ref_ids = entry["reference"]["reference_ids"]
            ref_items = [
                (rid, *id_to_obj[rid], f"Object {rid} ({id_to_obj[rid][1]})")
                for rid in ref_ids
            ]
        else:
            # category reference
            ref_items = [
                (None, rft, None, f"All objects of IFC type {rft}")
                for rft in entry["reference"]["reference_ifc_types"]
            ]

        # For each reference item, build a header and detail lines
        for a_id, a_type, a_name, ref_label in ref_items:
            against_value = entry["against"]["value"]
            header = (
                f"{ref_label}: is it \"{relation_text}\" with respect to "
                f"\"{against_value}\"? To check, we ran relations "
                f"{templates_list} between {ref_label} and {against_desc}."
            )

            details: List[str] = []
            for tpl_name in templates_list:
                # Gather positive relations for this reference and template
                rels_tpl = []
                for pr in positive_relations:
                    if pr["check_index"] != idx or pr["template"] != tpl_name:
                        continue
                    if a_id is not None and pr["a_id"] != a_id:
                        continue
                    rels_tpl.append(pr)

                if not rels_tpl:
                    continue

                verb = relation_phrases.get(tpl_name, tpl_name)
                target_list = ", ".join(
                    f"{pr['b_name']} (ID:{pr['b_id']})" for pr in rels_tpl
                )
                details.append(
                    f"The following objects {verb} {ref_label}: {target_list}."
                )

            # Combine header and details
            if details:
                summary = header + " " + " ".join(details)
            else:
                summary = header + " No positive relations found."

            summaries.append(summary)

    print(f"DEBUG: Built {len(summaries)} summaries.\n")
    return summaries

def process_checks(
    conn,
    all_objects: List[Tuple[int, str, str]],
    id_to_obj: Dict[int, Tuple[str, str]],
    all_ids: List[int],
    type_to_ids: Dict[str, List[int]],
    template_paths: Dict[str, Path],
    log_file
) -> Dict[str, Dict]:
    """
    Process each check in CHECKS: decompose, enrich, plan, execute spatial calls,
    build summaries, and evaluate rule compliance.

    Returns a dict mapping check_key → results dict.
    """
    pipeline_results: Dict[str, Dict] = {}

    for key, rule in CHECKS.items():
        print(f"\n=== Processing check: {key} ===")
        print(f"DEBUG: Rule text: {rule}\n")

        # A) Decompose rule into subchecks
        print("DEBUG: Decomposing rule...")
        decomposed = decompose_rule(rule, client)
        print("DEBUG: Decomposed checks:", json.dumps(decomposed, indent=2, ensure_ascii=False), "\n")

        # B) Enrich decomposed checks with entities from DB
        print("DEBUG: Enriching decomposed checks with entities...")
        enriched = extract_entities(decomposed, all_objects, client)
        print("DEBUG: Enriched entities:", json.dumps(enriched, indent=2, ensure_ascii=False), "\n")

        # C) Plan spatial queries using the LLM-based planner
        print("DEBUG: Planning spatial queries...")
        plan = spatial_planner(enriched, TEMPLATE_CATALOGUE, client)
        print("DEBUG: Spatial plan:", json.dumps(plan, indent=2, ensure_ascii=False), "\n")

        # D) Execute spatial calls and collect positive relations
        positive_relations = execute_spatial_calls(
            plan, id_to_obj, type_to_ids, all_ids, conn, template_paths, log_file
        )

        # E) Build human-readable summaries from positive relations
        summaries = build_summaries(plan, positive_relations, id_to_obj)

        # F) Evaluate rule compliance using the summaries and original rule
        print("DEBUG: Evaluating rule compliance...")
        evaluation = evaluate_rule(rule, summaries, client)
        print("DEBUG: Evaluation result:", json.dumps(evaluation, indent=2, ensure_ascii=False), "\n")

        # Collect all results for this check
        pipeline_results[key] = {
            "rule":              rule,
            "decomposed_checks": decomposed,
            "enriched_checks":   enriched,
            "spatial_plan":      plan,
            "positive_results":  positive_relations,
            "summaries":         summaries,
            "evaluation":        evaluation
        }

    return pipeline_results

# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    """
    Main entry point:
    1. Set up OpenAI key
    2. Load objects and mappings from DB
    3. Prepare template file paths
    4. Open log file for spatial calls
    5. Process all checks
    6. Write results to output JSON
    """
    # Configure OpenAI
    openai.api_key = MY_OPENAI_KEY
    global client
    client = openai

    # 1) Load all objects and build lookup maps
    all_objects, id_to_obj, all_ids, type_to_ids = load_objects_and_maps()

    # 2) Prepare template file paths for SQL execution
    template_paths = prepare_template_paths()

    # 3) Open a debug log for spatial calls
    log_path = Path(__file__).parent / "spatial_calls.log"
    print(f"DEBUG: Opening spatial calls log at {log_path} (append mode).")
    log_file = open(log_path, "w", encoding="utf-8")

    # 4) Connect to the database and process checks
    with get_connection() as conn:
        pipeline_results = process_checks(
            conn,
            all_objects,
            id_to_obj,
            all_ids,
            type_to_ids,
            template_paths,
            log_file
        )

    # Close the log file
    log_file.close()
    print("DEBUG: Closed spatial calls log.\n")

    # 5) Write pipeline results (including summaries) to JSON file
    output_path = Path(__file__).parent / "pipeline_output.json"
    print(f"DEBUG: Writing pipeline results to {output_path}.")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(pipeline_results, fp, ensure_ascii=False, indent=2)

    print("\nDone! Summaries and results written to pipeline_output.json")


if __name__ == "__main__":
    main()

    '''
    # ————— Define your checks —————
    checks = {
        "waste_check":         "Is waste and rubbish kept in a designated area?",
        "ignition_check":      "Have combustible materials been stored away from sources of ignition?",
        "fire_call_check":     "Are all fire alarm call points clearly signed and easily accessible?",
        "fire_escape_check1":  "Are all fire exit signs in place and unobstructed?",
        "fire_escape_check2":  "Are fire escape routes kept clear?",
        "fall_check":          "Is the condition of all flooring free from trip hazards?",
        "door_check":          "Are fire doors kept closed, i.e., not wedged open?",
        "extinguisher_check1": "Are portable fire extinguishers clearly labelled?",
        "extinguisher_check2": "Are all portable fire extinguishers readily accessible and not restricted by stored items?",
        "extinguisher_check3": "Are portable fire extinguishers either securely wall mounted or on a supplied stand?"
    }
    
    '''