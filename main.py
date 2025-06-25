from typing import Any, Dict, Optional, List, Literal, TypedDict
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
#from langgraph import PromptTemplate, LLMChain
from pipeline_helpers import *
from prompts.decompose_rule import decompose_rule
from prompts.extract_entities import extract_entities
from prompts.spatial_planner import spatial_planner
from prompts.decide_plan_polarity import decide_plan_polarity
from prompts.create_summaries import summarise_spatial_results
from prompts.evaluate_rule import evaluate_rule

import functools
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
#  Template catalogue  (key → SQL filename or None for composed funcs)
# ──────────────────────────────────────────────────────────────────────────
TEMPLATE_MAP: Dict[str, str | None] = {
    # 4‑param directionals
    "above": "above.sql",
    "below": "below.sql",
    "front": "front.sql",
    "behind": "behind.sql",
    "left": "left.sql",
    "right": "right.sql",
    # 3‑param distance
    "near": "near_far.sql",
    "far": "near_far.sql",
    # 2‑param boolean
    "touches": "touches.sql",
    # composed (executed in Python, no SQL file needed)
    "on_top_of": None,
    "leans_on": None,
    "affixed_to": None,
}

# Turn every SQL filename into a Path for db_utils
TEMPLATE_PATHS = {
    k: (Path(__file__).with_suffix("").parent / "sql" / v) if v else None
    for k, v in TEMPLATE_MAP.items()
}

TEMPLATE_CATALOGUE = {
    "touches": "True when two object bounding boxes are ≤ 0.1 m apart or intersect.",
    "front": "True when A is in front of B, within a small distance threshold.",
    "behind": "True when A is behind B, relative to the camera point of view, within a small threshold.",
    "left": "True when A is to the left of B, within a small distance threshold.",
    "right": "True when A is to the right of B, within a small distance threshold.",
    "above": "True when A is above B, within a small distance threshold.",
    "below": "True when A is below B, within a small distance threshold.",
    "on_top_of": "True when A is placed directly on top of B.",
    "leans_on": "True when A is supported by B.",
    "affixed_to": "True when A is affixed to B.",
    "near": "True when the distance between A and B is less than a defined threshold.",
    "far": "True when the distance between A and B is greater than a defined threshold."
}

def prepare_template_paths() -> Dict[str, Path]:
    """
    Prepare and return a dictionary mapping template names to their SQL file paths.
    """
    SQL_DIR = Path(__file__).parent / "sql"
    print(f"DEBUG: SQL directory is {SQL_DIR}")
    template_paths: Dict[str, Path] = {
        name: (SQL_DIR / fname) for name, fname in TEMPLATE_MAP.items() if fname
    }
    print(f"DEBUG: Prepared template paths for {len(template_paths)} SQL files.\n")
    return template_paths

class PipeState(TypedDict):
    rule_text: str
    decomposed_checks: Optional[dict]

    all_objects: Optional[List[Tuple[int, str, str]]]
    id_to_obj:   Optional[Dict[int, Tuple[str, str]]]
    all_ids:     Optional[List[int]]
    type_to_ids: Optional[Dict[str, List[int]]]

    enriched_checks: Optional[dict]
    spatial_plan: Optional[dict]
    relations: Optional[Any]
    summaries: Optional[List[str]]
    evaluation: Optional[dict]

class Evaluate_Hs_Rule:
    """
    A class for evaluating health and safety rules
    """
    def __init__(self, model_name: str = "gpt-4.1-mini-2025-04-14"):
        self.llm = get_llm(model_name=model_name)
        self.chain = None
        self.build_workflow()

    def build_workflow(self):
        workflow = StateGraph(PipeState)

        workflow.add_node("decompose rule", self.decompose_rule)
        workflow.add_node("load objects", self.load_objects)
        workflow.add_node("enrich checks", self.enrich_checks)
        workflow.add_node("spatial plan", self.spatial_plan)
        workflow.add_node("decide polarity", self.decide_polarity)
        workflow.add_node("execute planned relations", self.execute_planned_relations)
        workflow.add_node("summarise results", self.summarise_results)
        workflow.add_node("evaluate rule", self.evaluate_rule)

        workflow.add_edge(START,"load objects")
        workflow.add_edge("load objects", "decompose rule" )
        workflow.add_edge("decompose rule", "enrich checks")
        workflow.add_edge("enrich checks", "spatial plan")
        workflow.add_edge("spatial plan", "decide polarity")
        workflow.add_edge("decide polarity", "execute planned relations")
        workflow.add_edge("execute planned relations", "summarise results")
        workflow.add_edge("summarise results", "evaluate rule")
        workflow.add_edge("evaluate rule", END)

        self.workflow = workflow
        self.chain = workflow.compile()
        return self.chain

    def decompose_rule(self, state: PipeState) -> PipeState:
        state["decomposed_checks"] = decompose_rule(state["rule_text"], self.llm)
        return state

    def load_objects(self, state: PipeState) -> PipeState:
        all_objs, id2obj, ids, type2ids = load_objects_and_maps()
        state["all_objects"] = all_objs
        state["id_to_obj"] = id2obj
        state["all_ids"] = ids
        state["type_to_ids"] = type2ids
        return state

    def enrich_checks(self, state: PipeState) -> PipeState:
        enriched = extract_entities(
            state["decomposed_checks"],
            state["all_objects"],
            self.llm
        )
        state["enriched_checks"] = enriched
        return state

    def spatial_plan(self, state: PipeState) -> PipeState:
        plan = spatial_planner(
            state["enriched_checks"],
            TEMPLATE_CATALOGUE,
            self.llm
        )
        state["spatial_plan"] = plan
        return state

    def decide_polarity(self, state: PipeState) -> PipeState:
        decisioned = decide_plan_polarity(
            state["rule_text"],
            state.get("spatial_plan", {}),
            self.llm
        )
        state["spatial_plan"] = decisioned
        return state

    def execute_planned_relations(self, state: PipeState) -> PipeState:
        template_paths = prepare_template_paths()
        log_path = Path(__file__).parent / "spatial_calls.log"
        with open(log_path, "w", encoding="utf-8") as log_file:
            relations = execute_spatial_calls(
                state["spatial_plan"],
                state["id_to_obj"],
                state["type_to_ids"],
                state["all_ids"],
                template_paths,
                log_file
            )
        state["relations"] = relations
        return state

    def summarise_results(self, state: PipeState) -> PipeState:
        summaries = summarise_spatial_results(
            state.get("spatial_plan", {}),
            state.get("relations", []),
            self.llm
        )
        state["summaries"] = summaries
        return state

    def evaluate_rule(self, state: PipeState) -> PipeState:
        evaluation = evaluate_rule(
            state["rule_text"],
            state.get("summaries", []),
            self.llm
        )
        state["evaluation"] = evaluation
        return state

    def run_hs_rule_validator(self, rule_text: str) -> Dict[str, Any]:
        if self.chain is None:
            self.build_workflow()
        initial_state: PipeState = {
            "rule_text": rule_text,
            "decomposed_checks": None,
            "all_objects": None,
            "id_to_obj": None,
            "all_ids": None,
            "type_to_ids": None,
            "enriched_checks": None,
            "spatial_plan": None,
            "relations": None,
            "summaries": None,
            "evaluation": None,
        }
        return self.chain.invoke(initial_state)

    def visualize(self, engine: str = "mermaid", filename: Optional[Path] = None):
        """
        Display or save a visualization of the workflow graph.

        Parameters:
        - engine: "mermaid" (default) or "graphviz" for a more detailed node/edge view.
        - filename: Optional path to write the image file (png).
        """
        graph = self.chain.get_graph()
        # Choose rendering engine
        if engine == "graphviz":
            # Graphviz often includes richer node labels and layout
            img_bytes = graph.draw_graphviz(format="png")
        else:
            # Mermaid layout is lightweight and interactive in notebooks
            img_bytes = graph.draw_mermaid_png()
        # Optionally save to file
        if filename:
            with open(filename, "wb") as f:
                f.write(img_bytes)
            print(f"DEBUG: Workflow diagram saved to {filename}")
        # Display inline in Jupyter/IPython
        from IPython.display import display, Image

        return display(Image(img_bytes))

if __name__ == "__main__":
    # ————— Define your checks ————— 
    
    rules = {
        "extinguisher_check1": "Are all portable fire extinguishers readily accessible and not restricted by stored items?",
        "extinguisher_check2": "Are portable fire extinguishers either securely wall mounted or on a supplied stand?",
        "extinguisher_check3": "Are portable fire extinguishers clearly labelled?",
        "ignition_check":      "Have combustible materials been stored away from sources of ignition?",
    }

    # Prepare output directory
    outputs_dir = Path(__file__).parent / "outputs_results"
    outputs_dir.mkdir(exist_ok=True)

    validator = Evaluate_Hs_Rule()
    final_summary: Dict[str, Any] = {}
    

    # Iterate over each rule and run pipeline
    for name, text in rules.items():
        print(f"DEBUG: Processing rule '{name}'...")
        results = validator.run_hs_rule_validator(text)
        # Filter out large fields
        filtered = {k: v for k, v in results.items() if k not in ("all_objects", "all_ids","id_to_obj","type_to_ids")}
        # Per-rule output file
        rule_file = outputs_dir / f"{name}.json"
        print(f"DEBUG: Writing results for '{name}' to {rule_file}.")
        with open(rule_file, "w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)
        # Collect only the final evaluation for summary
        final_summary[name] = filtered.get("evaluation")

    # Write consolidated summary
    summary_file = outputs_dir / "final_results.json"
    print(f"DEBUG: Writing consolidated summary to {summary_file}.")
    with open(summary_file, "w", encoding="utf-8") as sf:
        json.dump(final_summary, sf, ensure_ascii=False, indent=2)

    print("Done! Individual rule outputs and final summary written to 'outputs_results'.")

    '''

    # Render and save workflow visualization
    graph = validator.chain.get_graph()
    png_bytes = graph.draw_mermaid_png()
    viz_path = Path(__file__).parent / "graph_workflow.png"
    with open(viz_path, "wb") as viz_file:
        viz_file.write(png_bytes)
    print(f"DEBUG: Workflow diagram saved to {viz_path}")
    '''


    # ──────────────────────────────────────────────────────────────────────────
# 1.  Define the H&S checks you want to run
# ──────────────────────────────────────────────────────────────────────────

'''
    # ————— Define your checks —————
    rules = {
        "waste_check":         "Is waste and rubbish kept in a designated area?", # Da aggiungere oggetto area
        "fire_call_check":     "Are all fire alarm call points clearly signed and easily accessible?", # si può fare facile
        "fire_escape_check1":  "Are all fire exit signs in place and unobstructed?", # si può fare facile
        "fire_escape_check2":  "Are fire escape routes kept clear?", # da aggiungere fire escape routes come oggetto
        "fall_check":          "Is the condition of all flooring free from trip hazards?", # da aggiungere routes come oggetto
        "door_check":          "Are fire doors kept closed, i.e., not wedged open?", # Da aggiungere attributo a porte


        "extinguisher_check1": "Are portable fire extinguishers clearly labelled?", # si può fare facile +
        "extinguisher_check2": "Are all portable fire extinguishers readily accessible and not restricted by stored items?", # Fatto +
        "extinguisher_check3": "Are portable fire extinguishers either securely wall mounted or on a supplied stand?" # Fatto +
        "ignition_check":      "Have combustible materials been stored away from sources of ignition?", # Fatto da integrare +
    }
    
    '''