import json
import re
from typing import List, Dict, Any

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)


def summarise_spatial_results(
    spatial_plan: Dict[str, Any],
    results: List[Dict[str, Any]],
    client,
    model: str = "gpt-4.1-mini-2025-04-14"
) -> List[str]:
    """
    Given a spatial plan and its filtered results, produce concise English
    summaries per check_index.
    """
    # 1) Build check summaries
    # Assuming extract_plan_descriptions is available
    check_descriptions = extract_plan_descriptions(spatial_plan)
    check_summaries = "\n".join(check_descriptions)

    # Serialize results
    results_json = json.dumps(results, indent=2, ensure_ascii=False)

    # Full task prompt unchanged, to be sent in the human message
    prompt_text = """
       <task_description>
        You receive two inputs:

        1️⃣  <check_summaries> – one line per check_index created from the spatial plan,  
            e.g.  
              Check 0: reference (category = "combustible materials") → IFC types ['IfcFurnishingElement', 'IfcBuildingElementProxy']; 
              tested template(s) ["far"] against IFC types ['IfcElectricDistributionPoint', 'IfcFlowTerminal']; keeping not-held (negative) matches.

              Check 1: reference (object = "portable fire extinguisher") → object IDs [1, 2, 3, 107, 109]; tested template(s) ["near"] against all objects in the DB; 
              keeping held (positive) matches.



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
        """

    # Build prompt template
    prompt_template = ChatPromptTemplate(
        input_variables=["check_summaries", "results_json", "rule"],
        messages=[
            SystemMessagePromptTemplate.from_template("Return valid JSON only."),
            HumanMessagePromptTemplate.from_template(
                prompt_text + "\n<check_summaries>\n{check_summaries}\n</check_summaries>" +
                "\n<results>\n{results_json}\n</results>"
            ),
        ],
    )

    # Format and invoke
    prompt_val = prompt_template.format_prompt(
        check_summaries=check_summaries,
        results_json=results_json
    )
    messages = prompt_val.to_messages()
    result = client.invoke(messages, model=model)

    # Extract content
    content = getattr(result, "content", str(result)).strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|```", "", content, flags=re.IGNORECASE).strip()

    # Parse JSON array of strings
    return json.loads(content)


def extract_plan_descriptions(spatial_plan: dict) -> List[str]:
    """
    Convert spatial_plan entries into one-line summaries per check_index.
    """
    descriptions: List[str] = []
    for plan in spatial_plan.get("plans", []):
        idx = plan["check_index"]
        ref = plan["reference"]
        ag = plan["against"]
        use_pos = plan.get("use_positive", True)

        # reference description
        if ref["type"] == "category":
            ref_desc = f'IFC types {ref.get("reference_ifc_types", [])}'
        elif ref["type"] == "object":
            ref_desc = f'object IDs {ref.get("reference_ids", [])}'
        else:
            ref_desc = "any object"

        # against description
        if ag["type"] == "category":
            ag_desc = f'IFC types {ag.get("against_ifc_types", [])}'
        elif ag["type"] == "object":
            ag_desc = f'object IDs {ag.get("against_ids", [])}'
        else:
            ag_desc = "all objects in the DB"

        # templates
        tmpl_names = [t["template"] for t in plan.get("templates", [])]
        tmpl_list = ", ".join(f'"{n}"' for n in tmpl_names)

        polarity = "held (positive)" if use_pos else "not-held (negative)"

        descriptions.append(
            f'Check {idx}: reference ({ref["type"]} = \"{ref["value"]}\") → {ref_desc}; '
            f'tested template(s) [{tmpl_list}] against {ag_desc}; keeping {polarity} matches.'
        )
    return descriptions
