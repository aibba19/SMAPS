import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from langchain_openai import ChatOpenAI
import os
import yaml
from dotenv import load_dotenv
from db_utils import *
from psycopg2 import sql

load_dotenv()

def get_openai_llm(model_name="gpt-4o-mini", api_key=None):
    """Get an OpenAI LLM instance."""
    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key or os.getenv("MY_OPENAI_KEY"),
    )

# Default LLM getter that can be modified based on preference
def get_llm(model_name='gpt-4.1-mini-2025-04-14'):
    """Get the default LLM instance."""
    # Change this function to use your preferred LLM
    return get_openai_llm(model_name)

# Load promtp usin yaml file
def load_prompt_by_name( target_name):
    base_dir = os.path.dirname(_file_)  # directory di utils.py
    file_path = os.path.join(base_dir, "Prompts", "prompts.yaml")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Expecting a list of dicts with 'name' and 'content' keys
    for item in data:
        if item.get('name') == target_name:
            return item.get('content')

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

def execute_spatial_calls(
    plan: Dict,
    id_to_obj: Dict[int, Tuple[str, str]],
    type_to_ids: Dict[str, List[int]],
    all_ids: List[int],
    #conn,
    template_paths: Dict[str, Path],
    log_file
) -> List[Dict]:
    """
    Execute spatial calls (SQL templates) for each entry in the plan, logging and collecting
    either positive or negative relations according to the entry's `use_positive` flag.

    Now reads `use_positive` from each plan entry:
      - If True, collects only held==True relations (as before).
      - If False, collects only held==False relations.
    """
    print("DEBUG: Executing spatial calls for each planned relation...")
   
    conn = get_connection()
    results: List[Dict] = []

    # Iterate through each planned check entry
    for entry in plan.get("plans", []):
        idx          = entry["check_index"]
        use_positive = entry.get("use_positive", True)
        print(f"DEBUG: check_index={idx}, use_positive={use_positive}")

        for tmpl in entry["templates"]:
            tpl_name = tmpl["template"]
            a_src, b_src = tmpl["a_source"], tmpl["b_source"]

            # Determine reference IDs (a_ids)
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

            # Determine against IDs (b_ids)
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

            # Run the spatial function 1-to-1 for each pair
            for a_id in a_ids:
                a_type, a_name = id_to_obj[a_id]
                for b_id in b_ids:
                    if a_id == b_id:
                        continue

                    b_type, b_name = id_to_obj[b_id]
                    call = {"type":"template","template":tpl_name,"a_id":b_id,"b_id":a_id}

                    # Log request
                    log_file.write("=== SPATIAL CALL ===\n")
                    log_file.write(json.dumps(call, ensure_ascii=False) + "\n")

                    result = run_spatial_call(conn, call, template_paths)

                    # Log result
                    log_file.write("RESULT:\n")
                    log_file.write(json.dumps(result, ensure_ascii=False) + "\n\n")
                    log_file.flush()

                    # Determine held
                    held = False
                    rows = result.get("rows", [])
                    relation_value = None
                    if rows:
                        first = rows[0]
                        # Here every query should be stantardized for optimization so the output can be accessed in the same way
                        if tpl_name == "touches":
                            held = bool(first[0]);       relation_value = first[1]
                        elif tpl_name in {"front","left","right","behind","above","below"}:
                            held = bool(first[3]);       relation_value = first[4] if held else None
                        elif tpl_name in {"near","far"}:
                            is_near = bool(first[2]);    is_far = bool(first[3])
                            held = is_near if tpl_name=="near" else is_far
                            relation_value = first[0]
                        else:  # composed relations
                            held = bool(first[0]);       relation_value = first[1] if len(first)>1 else None

                    # Record only if held matches use_positive
                    if held == use_positive:
                        results.append({
                            "check_index":    idx,
                            "template":       tpl_name,
                            "a_id":           a_id,
                            "a_name":         a_name,
                            "a_type":         a_type,
                            "b_id":           b_id,
                            "b_name":         b_name,
                            "b_type":         b_type,
                            "relation_value": relation_value
                        })

    print(f"DEBUG: Collected {len(results)} relations (use_positive={use_positive}).\n")
    return results