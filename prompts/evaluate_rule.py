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
        You must judge whether a health-and-safety rule is met, using only the
        spatial-query *summaries* provided.

        ●  The summaries already tell you  
           – which reference objects were tested,  
           – which other objects are (or are not) in the stated spatial relations,  
           – and, by omission, which reference objects produced **no** matches.

        ●  Treat every spatial result as geometrically correct, but feel free to doubt
           whether the named objects really matter for the rule.  If something seems
           mismatched or unclear, say so.

        For **each** summary:
          1. Decide  
                compliant   - the rule is satisfied for this case  
                violated    - the rule is broken (cite the objects)  
                undetermined- not enough information / object-type doubt
          2. Give a detailed explanation of the decision.  
             • If violated, list the object IDs / types that cause the breach.  
             • If uncertain, name the objects and state why (ambiguous type, etc.).

        Absence counts: if a reference object appears in the summary header but has
        no relation lines, infer the opposite relation held and use that evidence.

        Finally give an overall verdict:
          "overall_compliant" is **true** only when every entry is compliant.
          Otherwise it is false.
          In "overall_explanation" combine the reasons, naming any objects that break
          the rule or remain in doubt.

        Return valid **JSON only** in exactly this shape:

        {{
          "entry_results": [
            {{
              "summary": "<original summary>",
              "compliant": true | false | null,
              "explanation": "<short reason>"
            }},
            ...
          ],
          "overall_compliant": true | false,
          "overall_explanation": "<concise overall reason>"
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