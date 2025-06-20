# ---------------------------------------------------------------------------
# choose whether we want the held (positive) or NOT-held (negative) relations
# for each spatial plan
# ---------------------------------------------------------------------------
import json, re
from typing import Dict, List
import openai


def decide_plan_polarity(rule: str,
                         spatial_plan: Dict,
                         client,
                         model="gpt-4.1-mini-2025-04-14") -> Dict:
    """
    Add `"use_positive": true|false` to every plan entry.

    Parameters
    ----------
    rule          : original natural-language health-&-safety rule
    spatial_plan  : output from `spatial_planner` (dict with "plans")
    client        : OpenAI client (already holding the API key)
    model         : which model to call (default gpt-4o-mini)

    Returns
    -------
    The same dict but each item in spatial_plan["plans"] now also has
    `"use_positive": <bool>`.
    """

    plans = spatial_plan.get("plans", [])

    # ------------------------------------------------------------
    # 1. Build one-liner descriptions for the LLM
    # ------------------------------------------------------------
    desc_lines: List[str] = []
    for p in plans:
        rels = [tpl["template"] for tpl in p["templates"]]
        ref_val = p["reference"]["value"]
        ag_val  = p["against"]["value"]
        desc = (
            f"Plan {p['check_index']}: to verify '{p['relation_text']}' we will "
            f"check relations {rels} between '{ref_val}' and '{ag_val}'."
        )
        desc_lines.append(desc)

    descriptions = "\n".join(f"- {d}" for d in desc_lines)

    print("DEBUG: Built plan descriptions:")
    for d in desc_lines:
        print("  ", d)

    # ------------------------------------------------------------
    # 2. Compose prompt
    # ------------------------------------------------------------
    prompt = f"""
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

        <rule>
        {rule}
        </rule>

        <planned_tests>
        {descriptions}
        </planned_tests>
        """

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
    )

    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.I).strip()

    decisions = json.loads(content)["decisions"]

    # ------------------------------------------------------------
    # 3. Merge the decision back into the plans
    # ------------------------------------------------------------
    idx_to_flag = {d["check_index"]: d["use_positive"] for d in decisions}
    for p in plans:
        p["use_positive"] = idx_to_flag.get(p["check_index"], True)   # default True

    # Return updated structure
    spatial_plan["plans"] = plans

    #print("\nDEBUG: Final spatial_plan with use_positive flags:")
    #print(json.dumps(spatial_plan, indent=2, ensure_ascii=False))

    return spatial_plan