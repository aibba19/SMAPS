import json
import re
from typing import Dict, List, Tuple

from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)


def extract_entities(
    rule_json: Dict,
    objects: List[Tuple[int, str, str]],
    client,
    model: str = "gpt-4.1-mini-2025-04-14"
) -> Dict:
    """
    Enriches a decomposed H&S rule with concrete object IDs or IFC-type categories.

    Returns same structure as input, but each check gains:
      - "reference_ids": [ids...] or
      - "against_ids": [ids...] or
      - "reference_ifc_types" / "against_ifc_types": [types...]
    """
    # Prepare serialized inputs
    checks_str = json.dumps(rule_json.get("checks", []), indent=2, ensure_ascii=False)
    objects_md = "\n".join(
        f"- id={obj_id}, type={ifc_type}, name={name}"
        for obj_id, ifc_type, name in objects
    )

    # Full task prompt (unchanged)
    prompt_text = """
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
        """

    # Build the prompt template
    prompt_template = ChatPromptTemplate(
        input_variables=["checks_str", "objects_md"],
        messages=[
            SystemMessagePromptTemplate.from_template("Return valid JSON only."),
            HumanMessagePromptTemplate.from_template(
                prompt_text +
                "\n<checks>\n{checks_str}\n</checks>\n\n"
                "<available_objects>\n{objects_md}\n</available_objects>"
            ),
        ],
    )

    # Format and call LLM
    rendered = prompt_template.format_prompt(
        checks_str=checks_str,
        objects_md=objects_md
    ).to_messages()
    result = client.invoke(rendered, model=model)

    # Clean response
    content = getattr(result, "content", str(result)).strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|```", "", content, flags=re.IGNORECASE).strip()

    # Parse and return
    return json.loads(content)

