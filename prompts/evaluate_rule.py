import json
import re
from typing import List, Dict
import openai

def evaluate_rule(rule: str, summaries: List[str], client, model = "gpt-4.1-mini-2025-04-14" ) -> Dict:
    """
    Given a health-and-safety rule and a list of spatial-check summaries,
    ask the LLM whether the rule is respected, with a brief explanation.

    Returns a dict:
      {
        "compliant": true | false,
        "explanation": "<brief reason>"
      }
    """

    # Format summaries as bullet list
    summaries_md = "\n".join(f"- {s}" for s in summaries)

    prompt = f"""
        <task_description>
        You are given:
          1) A health-and-safety rule in natural language.
          2) A list of summaries, each describing results of spatial queries run on a PostGIS
             database where objects are represented by their 3D bounding boxes.

        Instructions:
          1. For each summary entry, decide if that specific case shows the rule is:
             - respected (compliant),
             - violated (non-compliant), or
             - undetermined (not enough data).
             Provide a one-sentence explanation for each entry.
          2. After evaluating all entries, give an overall determination:
             - “overall_compliant”: true if every entry is compliant (and none violated),
               false otherwise.
             - “overall_explanation”: rationale combining the per-entry outcomes.

        Output **JSON only** in this exact schema:
        {{
          "entry_results": [
            {{
              "summary":       "<original summary text>",
              "compliant":     true|false|null,
              "explanation":   "<reason or 'no enough data'>"
            }},
            …
          ],
          "overall_compliant":   true|false,
          "overall_explanation": "<overall rationale>"
        }}
        </task_description>

        <rule>
        {rule}
        </rule>

        <summaries>
        {summaries_md}
        </summaries>
        """

    resp = client.chat.completions.create(
        model= model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
    )

    content = resp.choices[0].message.content.strip()
    # strip code fences if any
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.IGNORECASE).strip()

    return json.loads(content)