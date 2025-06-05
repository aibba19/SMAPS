"""
Spatial planner
===============

Chooses which spatial queries to execute (from predefined templates **or**
custom SQL) to gather geometric evidence for a health‑and‑safety question.

Spatial context
---------------
* DB: PostgreSQL + PostGIS.
* Each object has a bounding‑box geometry column `geom`.
* Some relations are *view‑point‑independent* (bbox math is enough);
  others need a camera point‑of‑view (POV).

Template catalogue
------------------
View‑point‑independent
  • above       • below      • front
  • behind      • left       • right
  • near        • far        • touches

Camera / POV required
  • on_top_of   • leans_on   • affixed_to
    (If the user question does not give a camera/observer position,
     note that the relation cannot be evaluated.)

Return JSON
-----------
{
  "calls": [
    { "type": "template",
      "template": "above",
      "a": "Heater_01",
      "b": "CardboardBox_12",
      "requires_camera": false                       # optional, defaults false
    },
    { "type": "template",
      "template": "leans_on",
      "a": "Ladder_01",
      "b": "Wall_22",
      "requires_camera": true,
      "camera_available": false                      # include when POV missing
    },
    { "type": "sql",
      "sql": "SELECT ...",
      "purpose": "check 6 m clearance"
    }
  ]
}
"""

import json
import re

def plan_spatial_queries(user_question: str,
                         targets: list[dict],
                         queries: dict,
                         client) -> dict:
    """
    Decide which spatial queries (template or ad-hoc SQL) are needed,
    including object IDs in every call.
    """

    # Build lists for the prompt, now showing IDs
    targets_md = "\n".join(
        f"- ID: {t['id']}, {t['name']} ({t['ifc_type']}) – {t['description']}"
        for t in targets
    )

    templates_md = "\n".join(
        f"- {key}: {fname}"
        for key, fname in queries.items()
    )

    prompt = f"""
        <db_context>
        Database : PostgreSQL + PostGIS  
        Table    : room_objects(id INT, name TEXT, ifc_type TEXT, bbox GEOMETRY)

        You may call any PostGIS function/operator (ST_DWithin, ST_Intersects, &&, <->,
        ST_ZMin, ST_ZMax, ST_3DDistance, …). Every custom SQL **must** filter or join on
        the `id` column and use each object’s **exact** `name` in the SQL.
        </db_context>

        <task>
        **Goal – exhaustive spatial evidence.**  
        Generate every query needed to evaluate the user’s health-and-safety question.

        You receive **targets** (from entity-extraction) with `id`, `name`, `ifc_type`,
        `description`, and `reason`. Use that data to:

        1. **Relation focus**  
           In <available_objects> you already have the relevant objects from the database. 
           Your task is to determine which spatial relations to test—between those targets and any other objects (in the list or beyond) 
           that could influence the answer. 
           Focus solely on planning these relation checks; do not re-select or filter the targets.

        2. **Plan pairwise relations**  
           For any two objects requiring a direct spatial check, use a **template call**:
           choose from **<available_templates>**.

        3. **Obstruction & accessibility checks**  
           If the question involves access, restriction, or obstruction (e.g.
           “readily accessible”, “restricted by stored items”):
             - For each available object on what we need to check is spatial status, generate a **touches** template call against every other
               available object to detect contact (≤ 0.1 units).
             - Generate orientation template calls (`front`, `behind`, `left`, `right`,
               `above`, `below`) to verify clearance on all sides.

        4. **Custom SQL for complex logic**  
           Use as many custom SQL calls as needed (no limit) for N-to-N checks,
           aggregate counts, route clearance, etc. Each must be a complete, valid SQL
           statement run verbatim.

        5. **Camera-dependent templates**  
           For templates requiring a POV (`above`, `below`, `front`, `behind`, `left`,
           `right`, `on_top_of`, `leans_on`, `affixed_to`), set `"requires_camera": true`.
           If no camera is provided, also add `"camera_available": false`.

        6. **Consistency & coverage**  
           • Every object in the same role gets the same set of checks.  
           • Cover all needed combinations once; skip duplicates.

        ### Output schema (JSON only)
        {{
          "calls": [
            {{
              "type":           "template",
              "template":       "<template-name>",
              "a_id":           <int>, "a": "<name>",
              "b_id":           <int>, "b": "<name>",
              "requires_camera": <bool>,   # omit if false
              "camera_available":<bool>    # include only if requires_camera true
            }},
            {{
              "type":    "sql",
              "sql":     "<full SQL text>",
              "purpose": "<one-sentence reason>"
            }}
          ]
        }}

        ### Template descriptions
        - **touches**: returns true if two objects’ bounding boxes touch or are within 0.1 units.
        - **near/far**: returns a relation string and distance if objects are closer or farther than a threshold.
        - **above/below**: determines vertical relation relative to camera POV, returning a flag and relation.
        - **front/behind/left/right**: tests relative orientation from the camera’s viewpoint.
        - **on_top_of/leans_on/affixed_to**: higher-level predicates combining touches and orientation checks.

        Return **only** this JSON. No markdown, no code fences, no extra keys.
        </task>

        <user_question>
        {user_question}
        </user_question>

        <available_objects>
        {targets_md}
        </available_objects>

        <available_templates>
        {templates_md}
        </available_templates>
        """

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
    )

    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.I).strip()

    return json.loads(content)