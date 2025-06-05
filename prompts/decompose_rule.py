import json, re
from typing import Dict

def decompose_rule(hs_rule: str, client , model = "gpt-4.1-mini-2025-04-14" ) -> Dict:
    """
    Decompose a single health-and-safety rule into atomic checks.

    Example output:
    {
      "checks": [
        {
          "reference": { "type": "object",  "value": "Fire extinguisher" },
          "relation" : "unobstructed_by",
          "against"  : { "type": "category", "value": "stored items" }
        },
        {
          "reference": { "type": "category", "value": "Fire alarm call point" },
          "relation" : "clearly_signed",
          "against"  : { "type": "any" }
        }
      ]
    }

    Keys
    ----
    reference / against
        • type  : "object" | "category" | "any"
        • value : literal text taken from, or inferred from, the rule
    relation
        • Canonical verb / predicate describing what must be checked.
    """

    prompt = f"""
        <task>
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

        <rule>
        {hs_rule}
        </rule>
        """

    # LLM call
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

    return json.loads(content)
