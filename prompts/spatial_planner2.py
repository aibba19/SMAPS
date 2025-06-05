import json, re
from typing import Dict

def spatial_planner(checks_json: Dict,
                    template_catalogue: Dict[str, str],
                    client, model = "gpt-4.1-mini-2025-04-14") -> Dict:
    """
    Build a spatial-query plan from enriched checks.

    checks_json  : result of enrich_rule_with_objects()
    template_catalogue :
        e.g. {
          "touches" : "true if bboxes within 0.1 (incl. intersect)",
          "front"   : "object A is in front of B wrt camera POV",
          ...
        }

    Returns
    -------
    {
      "plans": [
        {
          "check_index": 0,
          "reference": { ...original reference block... },
          "against"  : { ...original against block...   },
          "templates": [
            { "template": "touches",
              "a_source": "reference_ids",
              "b_source": "against_ids|against_ifc_types|any_nearby" },
            { "template": "front",  ... },
            ...
          ]
        },
        ...
      ]
    }
    """

    # 1) Normalize checks_json → checks_list
    if isinstance(checks_json, list):
        checks_list = checks_json
    else:
        checks_list = checks_json.get("checks", [])

    # 2) Build template catalogue block for the prompt
    templates_md = "\n".join(
        f"- **{name}**: {desc}" for name, desc in template_catalogue.items()
    )

    # 3) Serialize checks_list rather than checks_json["checks"]
    checks_str = json.dumps(checks_list, indent=2, ensure_ascii=False)

    # ──────────────────────────────────────────────────────────────
    # 3. Prompt
    # ──────────────────────────────────────────────────────────────
    prompt = f"""
        <task>
        You will decide which template relations must be run for each check.

        Input
          • <checks_json>: result of the previous step (reference, against, relation,
            plus resolved IDs or IFC types).
          • <template_catalogue>: list of available 1-to-1 template predicates.

        Rules
          1. Use **templates first** for every relation that can be expressed as a
             pairwise predicate.
             Example: to test "unobstructed_by", run "touches", then
             "front/right/left/behind/above/below".
          2. When "against" or "reference" has "type":"any", indicate
                "b_source": "any_nearby"   or "a_source": "any_nearby"
             meaning the template will be executed later against *every* object found
             near the reference object.
          3. Keep the plan high-level; do not write raw SQL here.
          4. Preserve the order of checks.  Add a "check_index" so downstream code
             can align plan ↔ check.
          5. Return valid JSON **exactly** in the schema below.  No markdown.
          6. For each plan entry, include a field `"relation_text"` containing the
             original natural-language relation from the check (the value of the
             `"relation"` property).
          7. 

        Output schema
        {{
          "plans": [
            {{
              "check_index": <int>,
              "reference": {{ ... same as input ... }},
              "against"  : {{ ... same as input ... }},
              "templates": [
                {{
                  "template": "<template-name>",
                  "a_source": "reference_ids|reference_ifc_types|any_nearby",
                  "b_source": "against_ids|against_ifc_types|any_nearby"
                }},
                ...
              ]
            }},
            ...
          ]
        }}
        </task>

        <template_catalogue>
        {templates_md}
        </template_catalogue>

        <checks_json>
        {checks_str}
        </checks_json>
        """

    # ──────────────────────────────────────────────────────────────
    # 4. LLM call
    # ──────────────────────────────────────────────────────────────
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
    )

    # ──────────────────────────────────────────────────────────────
    # 5. Parse response
    # ──────────────────────────────────────────────────────────────
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json\\s*|\\s*```", "", content, flags=re.I).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        # Log the error and raw content for debugging
        print("⚠️ JSON parse error in spatial_planner:", e)
        print("Raw LLM output:\n", content)

        # Attempt simple cleanup: remove trailing commas before ] or }
        cleaned = re.sub(r",\s*(?P<closing>[\]\}])", r"\g<closing>", content)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Give up and rethrow so you can inspect the raw output
            print("⚠️ Cleanup attempt failed. Returning original exception.")
            raise
