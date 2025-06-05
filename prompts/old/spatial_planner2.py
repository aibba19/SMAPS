from typing import List, Tuple, Dict
import json, re

'''
Spatial planner
===============

Chooses which spatial queries to execute (from predefined templates **or**
custom SQL) to gather geometric evidence for a health-and-safety question.

Now receives the **entire object list** from the database and must decide
which objects matter.
'''

def plan_spatial_queries(
    user_question: str,
    objects: List[Tuple[int, str, str]],          # (id, ifc_type, name)
    templates: Dict[str, str],
    client,
) -> dict:

    # ------------------------------------------------------------
    # 1) Build the object list for the prompt
    # ------------------------------------------------------------
    objects_md = "\n".join(
        f"- ID: {obj_id}, {name} ({ifc_type})"
        for obj_id, ifc_type, name in objects
    )

    templates_md = "\n".join(f"- {k}: {v}" for k, v in templates.items())

    # ------------------------------------------------------------
    # 2) Prompt
    # ------------------------------------------------------------
    prompt = f'''
        <db_context>
        Database: PostgreSQL + PostGIS  
        Table  : room_objects(id INT, ifc_type TEXT, name TEXT, bbox GEOMETRY)

        Allowed PostGIS tools: ST_DWithin, ST_3DDistance, ST_Intersects, &&, <->,
        ST_ZMin, ST_ZMax …  
        Every custom SQL query **must** filter or join on `id`; use each object’s
        **exact `name`** string in the SQL you return.
        </db_context>

        <task>
        Produce **all** spatial queries needed to resolve the user’s
        health-and-safety question, prioritizing template calls for simple
        pairwise relations and reserving custom SQL for anything beyond.

        ### Two-step reasoning

        **Step 1 – Object selection**  
        • From <available_objects>, identify every object that can plausibly affect the
          answer (explicit mentions, implicit roles, possible obstacles, supports,
          hazards, etc.).  
        • Use id, ifc_type, name, description, and reason clues to infer functionality.  
        • Think in classes: if one extinguisher needs an accessibility check, *every*
          extinguisher needs the same checks; if something can be a “stored item”, treat
          any box / cabinet / shelf similarly.

        **Step 2 – Relation planning**  
        1. **Template calls (1-to-1)**  
           Use a template call *whenever* a single spatial predicate relates exactly two
           objects. Select templates only from **<available_templates>** below.

        2. **Custom SQL calls**  
           For any relation or complex logic not covered by a template—N-to-N checks,
           aggregate summaries, multi-step route clearance, non-pairwise predicates,
           or non-standard thresholds—return a *fully valid* SQL statement that can be
           executed directly against the `room_objects` table and its columns. Custom SQL
           must be independent of the template structure and run as-is.

        3. **Camera / POV templates**  
           For templates requiring POV (`above`, `below`, `front`, `behind`, `left`,
           `right`, `on_top_of`, `leans_on`, `affixed_to`), add  
           `"requires_camera": true`; if no camera is provided, also set  
           `"camera_available": false`.

        ### Output schema  (**JSON only**)
        {{
          "calls": [
            {{
              "type":        "template",
              "template":    "<template-name>",
              "a_id":        <int>,  "a": "<name>",
              "b_id":        <int>,  "b": "<name>",
              "requires_camera": <bool>,      # omit if false
              "camera_available": <bool>      # include only when requires_camera true
            }},
            {{
              "type":    "sql",
              "sql":     "<full SQL statement>",
              "purpose": "<why this query is necessary>"
            }}
          ]
        }}

        ### Guidelines
        * **Prefer templates for any two-object check.**  
        * **Use custom SQL only** when a relation is not expressible by the templates:
          it must be a complete, valid SQL query against `room_objects`.  
        * **Consistency:** every object in a given role must have the same relation
          checks.  
        * **Coverage & de-duplication:** cover all needed pairs/combinations once,
          skip duplicates.  
        * **Valid JSON only:** no markdown, no code fences, no extra keys.
        </task>

        <user_question>
        {user_question}
        </user_question>

        <available_objects>
        {objects_md}
        </available_objects>

        <available_templates>
        {templates_md}
        </available_templates>
        '''

    # ------------------------------------------------------------
    # 3) LLM call
    # ------------------------------------------------------------
    resp = client.chat.completions.create(
        model="o3-mini-2025-01-31",
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt},
        ],
    )

    # ------------------------------------------------------------
    # 4) Parse JSON safely
    # ------------------------------------------------------------
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.I).strip()

    return json.loads(content)


# Spatial planne2 code
'''
def main():
    # 1) OpenAI client
    openai.api_key = OPENAI_API_KEY
    client = openai

    # 2) Load all objects from DB
    all_objects = fetch_types_and_names()
    print(f"\nLoaded {len(all_objects)} IFC objects")

    results: Dict[str, dict] = {}

    with get_connection() as conn:
        for key, question in CHECKS.items():
            print(f"\n=== {key}: {question} ===")

            # 3) Spatial planning over full object set
            plan = plan_spatial_queries(
                user_question=question,
                objects=all_objects,
                templates=TEMPLATE_MAP,
                client=client,
            )
            calls = plan.get("calls", [])
            print("• Spatial-planner calls:")
            print(json.dumps(calls, indent=2, ensure_ascii=False))

            # 4) Execute each planned call
            executed_calls = []
            for idx, call in enumerate(calls, start=1):
                result = run_spatial_call(
                    conn,
                    call,
                    template_paths={k: p for k, p in TEMPLATE_PATHS.items() if p},
                )
                executed_calls.append(result)

                # Debug print
                status = result["status"]
                reason = result.get("reason")
                a_id = call.get("a_id")
                b_id = call.get("b_id")
                print(f"  └─ Call {idx}: {call['type']} {call.get('template','sql')} (a_id={a_id}, b_id={b_id}) => {status}", end="")
                if reason:
                    print(f"  ({reason})")
                else:
                    rows = result["rows"]
                    if rows:
                        print(f" — first row: {rows[0]}")
                    else:
                        print(" — 0 rows")

            # 5) Aggregate
            results[key] = {
                "question": question,
                "plan_calls": calls,
                "execution_results": executed_calls,
            }

    # 6) Dump final pipeline output
    with open("pipeline_output.json", "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)

    print("\nAll done — detailed trace saved to pipeline_output.json")

'''