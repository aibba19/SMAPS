import json
import re
from typing import Dict, List

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

def decide_plan_polarity(
    rule: str,
    spatial_plan: Dict,
    client,
    model: str = "gpt-4.1-mini-2025-04-14"
) -> Dict:
    """
    Add "use_positive" flags to each entry in spatial_plan["plans"].
    """
    # 1) Build plan descriptions
    plans = spatial_plan.get("plans", [])
    desc_lines: List[str] = []
    for p in plans:
        rels = [tpl["template"] for tpl in p["templates"]]
        ref_val = p["reference"]["value"]
        ag_val = p["against"]["value"]
        desc_lines.append(
            f"Plan {p['check_index']}: to verify '{p['relation_text']}' we will "
            f"check relations {rels} between '{ref_val}' and '{ag_val}'."
        )
    descriptions = "\n".join(f"- {d}" for d in desc_lines)

    # Full task prompt (unchanged)
    task_prompt = """
    <task>
    You are given:
      1) A health-and-safety rule.
      2) A list of planned spatial tests (“plans”), each with:
         - "relation_text": the natural-language requirement.
         - A corresponding template (e.g. "near", "touches").

    Your task is to choose **use_positive** for each plan so that the retained results
    expose any objects violating the rule:

    - **use_positive = true**  
      Keep the template-held results (relation holds).

    - **use_positive = false**  
      Keep the template-not-held results (relation does not hold).

    To decide:
    1. Look at **relation_text** and the **template** that tests it.
    2. Ask: “Does violation occur when the template relation holds, or when it fails?”

    Only consider setting use_positive = false when the template is near or far, and the goal of the rule is proximity-related (e.g., accessibility, separation, clearance).

    Use the following logic:

    If the rule requires objects to be near each other (e.g., for accessibility), then:

        If the template is near, set use_positive = true (we want to find actual nearby objects).

        If the template is far, set use_positive = false (we want to find cases where objects are not far ⇒ they are near).

    If the rule requires objects to be far from each other (e.g., fire separation), then:

        If the template is far, set use_positive = false (we want to find actual near objects that violate the rule).

        If the template is near, set use_positive = true (we want to find cases where objects are near thus violating the rule).

    Return **JSON only** in this schema:

    {{
      "decisions": [
        {{"check_index": 0, "use_positive": true|false}},
        …
      ]
    }}
    </task>
    """

    # Build prompt template
    human_template = (
        f"{task_prompt}\n\n"
        "<rule>{rule}</rule>\n\n"
        "<planned_tests>\n{descriptions}\n</planned_tests>"
    )

    prompt_template = ChatPromptTemplate(
        input_variables=["rule", "descriptions"],
        messages=[
            SystemMessagePromptTemplate.from_template("Return valid JSON only."),
            HumanMessagePromptTemplate.from_template(human_template),
        ],
    )

    # Format and render messages
    rendered = prompt_template.format_prompt(
        rule=rule,
        descriptions=descriptions
    ).to_messages()

    # Invoke the LLM
    result = client.invoke(rendered, model=model)

    # Extract and clean content
    content = getattr(result, "content", str(result)).strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.IGNORECASE).strip()

    # Parse decisions
    decisions = json.loads(content).get("decisions", [])

    # Merge back the use_positive flags
    idx_to_flag = {d["check_index"]: d["use_positive"] for d in decisions}
    for p in plans:
        p["use_positive"] = idx_to_flag.get(p["check_index"], True)
    spatial_plan["plans"] = plans

    return spatial_plan