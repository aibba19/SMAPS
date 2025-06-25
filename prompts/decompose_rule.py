import json
import re
from typing import Dict

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)

def decompose_rule(hs_rule: str, client, model: str = "gpt-4.1-mini-2025-04-14") -> Dict:
    """
    Decompose a single health-and-safety rule into atomic checks.
    """
    # Full task text (unchanged)
    prompt_text = """<task>
        You will convert one health-and-safety rule into a JSON plan for later
        spatial checks.

        Output **JSON only**:
        {{
          "checks": [
            {{
              "reference": {{ "type": "<object|category|any>", "value": "<text>" }},
              "relation" : "<canonical_relation>",
              "against"  : {{ "type": "<object|category|any>", "value": "<text>" }}
            }},
            …
          ]
        }}

        Guidelines
        1. Split the rule into the **smallest meaningful checks**. There may be one or
           many per rule.
        2. **reference** is the primary object or category named in the clause.
        3. **against** is the secondary object or category the relation is evaluated
           against. If the rule implies “free of any obstruction / any item”, set  
           {{ "type": "any", "value": "any object" }}.
        4. Use **type = "object"** when the rule names a specific item (e.g. “fire
           extinguisher”). Use **type = "category"** for generic groups (“stored items”,
           “obstacles”, “ignition sources”, …).
        5. Choose a concise **relation** string (e.g. "unobstructed_by", "clearly_signed",
           "mounted_on", "distance_gt" ).
        6. Do **not** invent extra checks. Do **not** repeat identical reference/against
           pairs.
        7. Return valid JSON only. No markdown, no code fences, no extra keys.
        </task>
        """

    # Append the actual rule
    human_content = f"{prompt_text}\n<rule>{hs_rule}</rule>"

    # Build a ChatPromptTemplate with a single system + single human message
    prompt_template = ChatPromptTemplate(
        input_variables=["hs_rule"],
        messages=[
            SystemMessagePromptTemplate.from_template("Return valid JSON only."),
            HumanMessagePromptTemplate.from_template(human_content),
        ],
    )

    # Render and invoke
    rendered = prompt_template.format_prompt(hs_rule=hs_rule).to_messages()
    result = client.invoke(rendered, model=model)

    # Clean and parse
    content = getattr(result, "content", str(result))
    if content.startswith("```"):
        content = re.sub(r"```json\s*|```\s*$", "", content, flags=re.IGNORECASE).strip()

    return json.loads(content)