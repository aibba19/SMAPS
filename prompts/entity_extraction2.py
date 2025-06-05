import json, re
from typing import List, Tuple, Dict

def extract_entities(rule_json: Dict,
                             objects: List[Tuple[int, str, str]],
                             client , model = "gpt-4.1-mini-2025-04-14" ) -> Dict:
    """
    Enriches a decomposed H&S rule with concrete object IDs or IFC-type
    categories.

    Parameters
    ----------
    rule_json : dict
        Output of `decompose_rule`, e.g. {"checks":[{...}, ...]}
    objects : list[(id, ifc_type, name)]
        All available DB objects.
    client : OpenAI client
        Configured ChatCompletion interface.

    Returns
    -------
    dict – same structure as input, but each check gains either
           • "reference_ids": [ids...]  OR
           • "against_ids"  : [ids...]
           • "against_ifc_type": "<IfcType>"
    """

    # ------------------------------------------------------------------
    # 1. Build text block of objects
    # ------------------------------------------------------------------
    objects_md = "\n".join(
        f"- id={obj_id}, type={ifc_type}, name={name}"
        for obj_id, ifc_type, name in objects
    )

    # 2. Original checks as JSON string (passed to the LLM)
    checks_str = json.dumps(rule_json["checks"], indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 3. Prompt
    # ------------------------------------------------------------------
    prompt = f"""
        <task>
        You will map each *reference* / *against* entry in the supplied checks to
        actual objects (by id) or IFC-type categories from <available_objects>.

        Rules
        • If "type" == "object": find EVERY object whose *name* or *ifc_type* matches
          logically (synonyms allowed, case-insensitive).  Return their ids in
          "reference_ids" or "against_ids".
        • If "type" == "category": choose the most appropriate IFC type or types that
          represent that category and add:
             "against_ifc_types": ["<IfcType1>", "<IfcType2>", ...]
          (or "reference_ifc_types" if the category is in the reference field).
          You may include multiple IFC types if more than one class is relevant.

        • Matching is logical, not literal.  Example: "fire extinguisher" should match
          any object named like "Extg_01" or type that denotes
          extinguishers in the dataset.
        • Do not invent ids or IFC types that are not in <available_objects>.
        • Preserve every other field unchanged.
        • Return valid JSON only (no markdown, code fences, or extra keys).
        • For the ‘any object’ category, don’t enumerate individual IDs—just return ‘all IDs’.
        </task>

        <checks>
        {checks_str}
        </checks>

        <available_objects>
        {objects_md}
        </available_objects>
        """

    # ------------------------------------------------------------------
    # 4. LLM call
    # ------------------------------------------------------------------
    resp = client.chat.completions.create(
        model= model,
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
    )

    # ------------------------------------------------------------------
    # 5. Parse
    # ------------------------------------------------------------------
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json\\s*|\\s*```", "", content, flags=re.I).strip()

    enriched = json.loads(content)
    return enriched
