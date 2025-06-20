import json
import re
from tabnanny import check
from typing import Dict, List, Any
import openai

def summarise_spatial_results(spatial_plan: Dict[str, Any],
                              results: List[Dict[str, Any]],
                              client,
                              model: str = "gpt-4.1-mini-2025-04-14") -> List[str]:
    """
    Given a spatial plan and its filtered results, produce one concise
    English summary per check_index.

    Input:
      spatial_plan: {
        "plans": [ { check_index, reference, against, templates, relation_text, use_positive }, … ]
      }
      results: [
        { check_index, template, a_id, a_name, b_id, b_name, relation_value }, …
      ]
      client: OpenAI client
      model:  LLM model name

    Output:
      A List[str] where each string summarizes one check_index, e.g.:
        ["Check 0: Object 97 …", "Check 1: Object 1 …", …]
    """

    check_descriptions = extract_plan_descriptions(spatial_plan)

    #for d in check_descriptions:
     #   print (d)

    prompt = f"""
        <task_description>
        You receive two inputs:

        1️⃣  <check_summaries> – one line per check_index created from the spatial plan,  
            e.g.  
              Check 0: reference (category = "combustible materials") → IFC types ['IfcFurnishingElement', 'IfcBuildingElementProxy']; tested template(s) ["far"] against IFC types ['IfcElectricDistributionPoint', 'IfcFlowTerminal']; keeping not-held (negative) matches.

              Check 1: reference (object = "portable fire extinguisher") → object IDs [1, 2, 3, 107, 109]; tested template(s) ["near"] against all objects in the DB; keeping held (positive) matches.



        2️⃣  <results> – a JSON array in which **each row is a POSITIVE match**
            (already filtered by “use_positive”).  
              {{
                "check_index": 0,
                "template"   : "touches",
                "a_id"       : …, "a_name": …, "a_type": …,
                "b_id"       : …, "b_name": …, "b_type": …,
                "relation_value": "…"
              }}

        --------------------------------------------------------------------
        Your task – produce **one compact sentence per check_index**:

        A.  First clause: restate the check summary (reference targets, template list,  
            polarity) so a reader remembers what was tested.

        B.  For **every reference object / IFC-type mentioned in the check summary**:

            • If at least one result row exists (same check_index and a_id / a_type),
              list **every** target object, using the supplied *relation_value* text
              verbatim.

            • If **no row** exists for that reference, add  
              “No objects met the tested relation for <reference>.”

            (This covers both held-and-kept vs. not-held-and-kept cases.)

        Return your output as a JSON **array of strings** –  
        for example:

        [
          "Check 0: … sentence …",
          "Check 1: … sentence …"
        ]

        No markdown, no code fences, no extra keys.
        </task_description>

        <check_summaries>
        {chr(10).join(check_descriptions)}
        </check_summaries>

        <results>
        {json.dumps(results, indent=2, ensure_ascii=False)}
        </results>
        """

    #print("DEBUG: Prompt for summarisation:")
    #print(prompt)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return JSON array only."},
            {"role": "user",   "content": prompt}
        ],
    )

    content = resp.choices[0].message.content.strip()
    #print("DEBUG: Raw LLM response:")
    #print(content)

    # Strip code fences if any
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.I).strip()

    # Now parse directly as a JSON array
    try:
        summaries = json.loads(content)
    except json.JSONDecodeError as e:
        print("ERROR parsing summaries JSON:", e)
        # Fallback: return the raw text as single-element list
        return [content]

    return summaries


def extract_plan_descriptions(spatial_plan: dict) -> list[str]:
    """
    Given a spatial_plan dict, return one concise string per check_index summarizing:
      – reference type/value → underlying IFC types or object IDs
      – which template(s) were run
      – against which targets (IFC types, object IDs, or all objects)
      – whether we’re keeping positive (held) or negative (not-held) matches
    """
    descriptions = []
    for plan in spatial_plan.get("plans", []):
        idx     = plan["check_index"]
        ref     = plan["reference"]
        ag      = plan["against"]
        use_pos = plan["use_positive"]

        # reference description
        if ref["type"] == "category":
            ref_desc = f'IFC types {ref["reference_ifc_types"]}'
        elif ref["type"] == "object":
            ref_desc = f'object IDs {ref["reference_ids"]}'
        else:  # any
            ref_desc = "any object"

        # against description
        if ag["type"] == "category":
            ag_desc = f'IFC types {ag["against_ifc_types"]}'
        elif ag["type"] == "object":
            ag_desc = f'object IDs {ag["against_ids"]}'
        else:  # any
            ag_desc = "all objects in the DB"

        # templates
        tmpl_names = [t["template"] for t in plan.get("templates", [])]
        tmpl_list  = ", ".join(f'"{n}"' for n in tmpl_names)

        # polarity
        polarity = "held (positive)" if use_pos else "not-held (negative)"

        descriptions.append(
            f'Check {idx}: reference ({ref["type"]} = "{ref["value"]}") → {ref_desc}; '
            f'tested template(s) [{tmpl_list}] against {ag_desc}; '
            f'keeping {polarity} matches.'
        )

    return descriptions