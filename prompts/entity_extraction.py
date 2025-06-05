import json
import re
from typing import List, Tuple, Union

def extract_entities(user_question: str,
                     objects: List[Tuple[int, str, str]],
                     client) -> dict:
    """
    Given a user_question and a list of (id, ifc_type, name) tuples, call the LLM and
    return a dict of the form:

        {
          "targets": [
             {
               "id":          123,
               "ifc_type":    "<IfcWall>",
               "name":        "External_Wall_42",
               "description": "External cavity wall on south façade",
               "reason":      "It could block the fire-escape route"
             },
             ...
          ]
        }

    Keys:
      • id          – the database identifier for the object
      • description – short plain-English phrase (≤15 words) describing the object
      • reason      – one-sentence (≤20 words) why this object is relevant
    """

    # 1) Format the available objects as a bullet list including IDs
    objects_list = "\n".join(
        f"- ID: {obj_id}, {ifc_type} → {name}"
        for obj_id, ifc_type, name in objects
    )

    # 2) Construct the prompt
    prompt = f"""
        <task_description>
        You are an assistant mapping natural-language health-and-safety questions to IFC objects from a building database.

        Input:
        • A user question about a building.
        • A bullet list of objects with their database IDs, IFC types, and names.

        Output (JSON only):
        {{
          "targets": [
            {{
              "id":          <integer>,      # exactly as provided in the available_objects
              "ifc_type":    "<IfcType>",    # exactly as provided in the available_objects
              "name":        "<ObjName>",    # exactly as provided in the available_objects
              "description": "<brief plain-English description>",
              "reason":      "<sentence explaining relevance>"
            }},
            ...
          ]
        }}

        Guidelines :

        1. **Include all potentially relevant objects**  
           Do not omit indirect participants. 
           For example, if the question involves fire extinguishers, include *every* fire extinguisher listed in `<available_objects>`.

        2. **Category expansion**  
           If the question refers to a broad category (e.g., “stored items”, “obstacles”, “ignition sources”), 
           you **must** include all objects whose IFC type or name suggests they belong to that category.  
           These categories are interpreted as follows:

           • **Stored items - Obstacles - Blocking Elements**: any type of objects.  
             Example types include (but are not limited to): boxes, cabinets, containers, shelves, pallets,
             chairs, desks, tables, planters, partitions, furniture.

           • **Ignition sources / heat-generating elements**: objects that may pose a fire risk due to electrical or thermal components.  
             Example types include: heaters, boilers, sockets, cooktops, lighting fixtures.

           • **Affixing objects**: surfaces or structural elements to which other items can be mounted, attached, or fixed in place.  
              These may serve as physical supports for signage, equipment, safety devices, or storage components.  
              Common examples (not exhaustive) include:  
              walls, columns, partitions, panels, desks, doors, windows, lockers, cabinets, beams, pillars, ceilings, handrails, 
              railings, support frames, posts, structural boards, and storage units.

              Include any object that can realistically act as a mounting surface within an interior environment.

           These examples are not exhaustive. Include **any object** from the list that could reasonably fit the category, 
           even if not explicitly mentioned in the question.

        3. Use provided IDs / names exactly; do not invent or alter them.

        4. No limit on list size—include as many objects as necessary.

        5. Return valid JSON only (no markdown, code fences, or extra keys).
        </task_description>

        <user_question>
        {user_question}
        </user_question>

        <available_objects>
        {objects_list}
        </available_objects>
        """  


    # 3) Call the LLM
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # or "o4-mini-2025-04-16"
        messages=[
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user",   "content": prompt}
        ],
    )

    # 4) Parse the response
    content = resp.choices[0].message.content.strip()
    if content.startswith("```"):
        content = re.sub(r"```json\s*|\s*```", "", content, flags=re.IGNORECASE).strip()

    return json.loads(content)