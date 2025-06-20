import os
import json
import openai
from typing import List, Dict
from config import *

# Import the function you want to test
from prompts.evaluate_rule import evaluate_rule
from prompts.decide_plan_polarity import decide_plan_polarity
from prompts.create_summaries import summarise_spatial_results

# Make sure your OPENAI_API_KEY is set in the environment
openai.api_key = MY_OPENAI_KEY

def test_evaluate_rule():
    # The health‐and‐safety rule to test
    rule = (
        "Are all portable fire extinguishers readily accessible and not "
        "restricted by stored items?"
    )

    # Fire ext id 1:
#   Front -> {}  
#   Left  -> {"furniture": [34, 67]}  
#   Right -> {"wall": [52]}  
#   Above -> {}  
#   Below -> {"floor": [46]}  
#
# Fire ext id 2:
#   Near  -> {"wall": [49, 50]}  
#   Front -> {}  
#   Left  -> {"furniture":[700,701]}   
#   Right -> {"furniture":[600,601]}   
#   Above -> {"sign": [12]}   
#   Below -> {"furniture": [600,601]}   
#
# Fire ext id 3:
#   Near  -> {"panel": [38, 36]}  
#   Front -> {"panel": [36]}  
#   Left  -> {}  
#   Right -> {"furinture":[chair 198]}  
#   Above -> {}  
#   Below -> {""furniture":[table 789]}  
#
# Fire ext id 107:
#   Near  -> {"door": [17, 87]}  
#   Front -> {}  
#   Left  -> {}  
#   Right -> {}  
#   Above -> {}  
#   Below -> {}  
#
# Fire ext id 109:
#   Near  -> {"chair": [98, 99]}  
#   Front -> {"chair": [98, 99]}  
#   Left  -> {"chair": [99]}  
#   Right -> {"chair": [98, 99]}  
#   Above -> {}  
#   Below -> {"chair": [98, 99]} 

    summaries: List[str] = [
    # Fire ext id 1
    "Object 1 (Fire_Safety-Nystrom-ABC_Dry_Chemical_Portable_Fire_Extinguisher:EX-3002:323036): "
    "is it \"readily_accessible\" with respect to \"any object\"? To check, we ran relations "
    "['touches', 'front', 'left', 'right', 'above', 'below'] between Object 1 and all objects in the DB. "
    "The following objects touch Object 1: Basic Wall:Wall-Fnd_300Con_Footing:314801 (ID:52). "
    "The following objects are to the left of Object 1: Furniture_Chair_Modern:Oak_Armchair:340234 (ID:34), "
    "Furniture_Chair_Modern:Oak_Armchair:340567 (ID:67). "
    "The following objects are below Object 1: Floor:Concrete_Slab:317594 (ID:46).",

    # Fire ext id 2
    "Object 2 (Fire_Safety-Nystrom-ABC_Dry_Chemical_Portable_Fire_Extinguisher:EX-3002:323764): "
    "is it \"readily_accessible\" with respect to \"any object\"? To check, we ran relations "
    "['near', 'front', 'left', 'right', 'above', 'below'] between Object 2 and all objects in the DB. "
    "The following objects are near Object 2: Basic Wall:Wall-Fnd_300Con_Footing:314130 (ID:49), "
    "Basic Wall:Wall-Fnd_300Con_Footing:314254 (ID:50). "
    "The following objects are to the left of Object 2: Furniture_Cabinet_Small:Storage_Box:700 (ID:700), "
    "Furniture_Cabinet_Small:Storage_Box:701 (ID:701). "
    "The following objects are to the right of Object 2: Furniture_Cabinet_Large:Wood_Crate:600 (ID:600), "
    "Furniture_Cabinet_Large:Wood_Crate:601 (ID:601). "
    "The following objects are above Object 2: Safety_Signage:Exit_Sign:12 (ID:12). "
    "The following objects are below Object 2: Furniture_Table_Round:Dining_Table:600 (ID:600), "
    "Furniture_Table_Round:Dining_Table:601 (ID:601).",

    # Fire ext id 3
    "Object 3 (Fire_Safety-Nystrom-ABC_Dry_Chemical_Portable_Fire_Extinguisher:EX-3002:323956): "
    "is it \"readily_accessible\" with respect to \"any object\"? To check, we ran relations "
    "['near', 'front', 'right', 'below'] between Object 3 and all objects in the DB. "
    "The following objects are near Object 3: Panel_Control:Control_Panel:38 (ID:38), "
    "Panel_Control:Control_Panel:36 (ID:36). "
    "The following objects are in front of Object 3: Panel_Control:Control_Panel:36 (ID:36). "
    "The following objects are to the right of Object 3: Furniture_Chair_Lounge:Recliner:198 (ID:198). "
    "The following objects are below Object 3: Furniture_Table_Small:Side_Table:789 (ID:789).",

    # Fire ext id 107
    "Object 107 (Fire_Safety-Nystrom-ABC_Dry_Chemical_Portable_Fire_Extinguisher:EX-3002:323045): "
    "is it \"readily_accessible\" with respect to \"any object\"? To check, we ran relations "
    "['near', 'front', 'right', 'left', 'behind', 'above', 'below'] between Object 107 and all objects in the DB. "
    "The following objects are near Object 107: Door_Internal:Single_Door:318669 (ID:17), "
    "Door_Internal:Single_Door:318669:1 (ID:87).",

    # Fire ext id 109
    "Object 109 (Fire_Safety-Nystrom-ABC_Dry_Chemical_Portable_Fire_Extinguisher:EX-3002:323069): "
    "is it \"readily_accessible\" with respect to \"any object\"? To check, we ran relations "
    "['near', 'front', 'right', 'left', 'behind', 'above', 'below'] between Object 109 and all objects in the DB. "
    "The following objects are near Object 109: Furniture_Chair_Viper:1120x940x350mm:340520 (ID:98), "
    "Furniture_Chair_Viper:1120x940x350mm:340707 (ID:99). "
    "The following objects are in front of Object 109: Furniture_Chair_Viper:1120x940x350mm:340520 (ID:98), "
    "Furniture_Chair_Viper:1120x940x350mm:340707 (ID:99). "
    "The following objects are to the right of Object 109: Furniture_Chair_Viper:1120x940x350mm:340520 (ID:98), "
    "Furniture_Chair_Viper:1120x940x350mm:340707 (ID:99). "
    "The following objects are to the left of Object 109: Furniture_Chair_Viper:1120x940x350mm:340707 (ID:99). "
    "The following objects are behind Object 109: Furniture_Chair_Viper:1120x940x350mm:340520 (ID:98). "
    "The following objects are below Object 109: Furniture_Chair_Viper:1120x940x350mm:340520 (ID:98), "
    "Furniture_Chair_Viper:1120x940x350mm:340707 (ID:99).",
    ]

    result = evaluate_rule(rule, summaries, openai)
    print(json.dumps(result, indent=2))



def test_decide_plan_polarity():
    # The health-and-safety rule
    rule = (
        "Are all portable fire extinguishers readily accessible and not "
        "restricted by stored items?"
    )

    # Simulated output from spatial_planner
    spatial_plan = {
        "plans": [
            {
                "check_index": 0,
                "reference": {
                    "type": "object",
                    "value": "portable fire extinguisher",
                    "reference_ids": [1, 2, 3, 107, 109]
                },
                "against": {
                    "type": "any",
                    "value": "any object",
                    "against_ids": "all IDs"
                },
                "templates": [
                    {"template": "near", "a_source": "reference_ids", "b_source": "any_nearby"}
                ],
                "relation_text": "readily_accessible"
            },
            {
                "check_index": 1,
                "reference": {
                    "type": "object",
                    "value": "portable fire extinguisher",
                    "reference_ids": [1, 2, 3, 107, 109]
                },
                "against": {
                    "type": "category",
                    "value": "stored items",
                    "against_ifc_types": [
                        "IfcFurnishingElement",
                        "IfcBuildingElementProxy"
                    ]
                },
                "templates": [
                    {"template": "touches",  "a_source": "reference_ids", "b_source": "against_ifc_types"},
                    {"template": "front",    "a_source": "reference_ids", "b_source": "against_ifc_types"},
                    {"template": "right",    "a_source": "reference_ids", "b_source": "against_ifc_types"},
                    {"template": "left",     "a_source": "reference_ids", "b_source": "against_ifc_types"},
                    {"template": "behind",   "a_source": "reference_ids", "b_source": "against_ifc_types"},
                    {"template": "above",    "a_source": "reference_ids", "b_source": "against_ifc_types"},
                    {"template": "below",    "a_source": "reference_ids", "b_source": "against_ifc_types"}
                ],
                "relation_text": "unobstructed_by"
            }
        ]
    }

    rule2 = "Have combustible materials been stored away from sources of ignition?"
    # Is there any combustible material stored away of source of ignition?
    # Is there any combustible material near source of ignition?

    spatial_plan2 = {
        "plans": [
            {
                "check_index": 0,
                "reference": {
                    "type": "category",
                    "value": "combustible materials",
                    "reference_ifc_types": [
                        "IfcFurnishingElement"
                    ]
                },
                "against": {
                    "type": "category",
                    "value": "sources of ignition",
                    "against_ifc_types": [
                        "IfcElectricDistributionPoint",
                        "IfcFlowTerminal",
                        "IfcBuildingElementProxy"
                    ]
                },
                "templates": [
                    {
                        "template": "far",
                        "a_source": "reference_ifc_types",
                        "b_source": "against_ifc_types"
                    }
                ],
                "relation_text": "stored_away_from"
            }
        ]
    }
    

    # Call our function to decide polarity
    enriched_plan = decide_plan_polarity(rule2, spatial_plan2, openai)

    # Print the result for inspection
    print(json.dumps(enriched_plan, indent=2, ensure_ascii=False))


def test_summarise_spatial_results():

    # Define the spatial_plan input
    spatial_plan = {
        "plans": [
            {
                "check_index": 0,
                "reference": {
                    "type": "category",
                    "value": "combustible materials",
                    "reference_ifc_types": [
                        "IfcFurnishingElement",
                        "IfcBuildingElementProxy"
                    ]
                },
                "against": {
                    "type": "category",
                    "value": "sources of ignition",
                    "against_ifc_types": [
                        "IfcElectricDistributionPoint",
                        "IfcFlowTerminal"
                    ]
                },
                "templates": [
                    {
                        "template": "far",
                        "a_source": "reference_ifc_types",
                        "b_source": "against_ifc_types"
                    }
                ],
                "relation_text": "distance_gt",
                "use_positive": False
            },

            {
          "check_index": 3,
          "reference": {
            "type": "object",
            "value": "portable fire extinguisher",
            "reference_ids": [
              1,
              2,
              3,
              107,
              109
            ]
          },
          "against": {
            "type": "any",
            "value": "any object",
            "against_ids": "all IDs"
          },
          "templates": [
            {
              "template": "near",
              "a_source": "reference_ids",
              "b_source": "any_nearby"
            }
          ],
          "relation_text": "readily_accessible",
          "use_positive": True
        },
        {
          "check_index": 1,
          "reference": {
            "type": "object",
            "value": "portable fire extinguisher",
            "reference_ids": [
              1,
              2,
              3,
              107,
              109
            ]
          },
          "against": {
            "type": "category",
            "value": "stored items",
            "against_ifc_types": [
              "IfcFurnishingElement",
              "IfcBuildingElementProxy"
            ]
          },
          "templates": [
            {
              "template": "touches",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            },
            {
              "template": "front",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            },
            {
              "template": "right",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            },
            {
              "template": "left",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            },
            {
              "template": "behind",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            },
            {
              "template": "above",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            },
            {
              "template": "below",
              "a_source": "reference_ids",
              "b_source": "against_ifc_types"
            }
          ],
          "relation_text": "unobstructed_by",
          "use_positive": True
        }
        ]
    }

    # 3) Define the results input
    results = [
        {
            "check_index": 0,
            "template": "far",
            "a_id": 97,
            "a_name": "Furniture_Chair_Desk_w-Armrest_2:635x686x380mm:339684",
            "a_type": "IfcFurnishingElement",
            "b_id": 82,
            "b_name": "computer monitor:Default:347410",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347410 (ID:82) is near Furniture_Chair_Desk_w-Armrest_2:635x686x380mm:339684 (ID:97)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 97,
            "a_name": "Furniture_Chair_Desk_w-Armrest_2:635x686x380mm:339684",
            "a_type": "IfcFurnishingElement",
            "b_id": 83,
            "b_name": "computer monitor:Default:347668",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347668 (ID:83) is near Furniture_Chair_Desk_w-Armrest_2:635x686x380mm:339684 (ID:97)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 101,
            "a_name": "small plant:Ny märkning:346329",
            "a_type": "IfcFurnishingElement",
            "b_id": 82,
            "b_name": "computer monitor:Default:347410",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347410 (ID:82) is near small plant:Ny märkning:346329 (ID:101)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 101,
            "a_name": "small plant:Ny märkning:346329",
            "a_type": "IfcFurnishingElement",
            "b_id": 83,
            "b_name": "computer monitor:Default:347668",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347668 (ID:83) is near small plant:Ny märkning:346329 (ID:101)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 102,
            "a_name": "Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346445",
            "a_type": "IfcFurnishingElement",
            "b_id": 82,
            "b_name": "computer monitor:Default:347410",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347410 (ID:82) is near Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346445 (ID:102)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 102,
            "a_name": "Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346445",
            "a_type": "IfcFurnishingElement",
            "b_id": 83,
            "b_name": "computer monitor:Default:347668",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347668 (ID:83) is near Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346445 (ID:102)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 103,
            "a_name": "Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346857",
            "a_type": "IfcFurnishingElement",
            "b_id": 82,
            "b_name": "computer monitor:Default:347410",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347410 (ID:82) is near Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346857 (ID:103)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 103,
            "a_name": "Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346857",
            "a_type": "IfcFurnishingElement",
            "b_id": 83,
            "b_name": "computer monitor:Default:347668",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347668 (ID:83) is near Desk with Power strip:5-M-EXEC-SD-EXM4DSLF34-VWA-BL:346857 (ID:103)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 104,
            "a_name": "Desk:Desk SONITUS 1800x760x800mm:346873",
            "a_type": "IfcFurnishingElement",
            "b_id": 78,
            "b_name": "HAFELE_Powerdocks_Power-Fit-Power-Outlet-Box-with-Recessed:With Recessed Supply Unit-826.66.014:351601",
            "b_type": "IfcElectricDistributionPoint",
            "relation_value": "HAFELE_Powerdocks_Power-Fit-Power-Outlet-Box-with-Recessed:With Recessed Supply Unit-826.66.014:351601 (ID:78) is near Desk:Desk SONITUS 1800x760x800mm:346873 (ID:104)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 104,
            "a_name": "Desk:Desk SONITUS 1800x760x800mm:346873",
            "a_type": "IfcFurnishingElement",
            "b_id": 84,
            "b_name": "computer monitor:Default:347814",
            "b_type": "IfcFlowTerminal",
            "relation_value": "computer monitor:Default:347814 (ID:84) is near Desk:Desk SONITUS 1800x760x800mm:346873 (ID:104)"
        },
        {
            "check_index": 0,
            "template": "far",
            "a_id": 11,
            "a_name": "3 Phase Socket Outlet:Standard:349141",
            "a_type": "IfcBuildingElementProxy",
            "b_id": 77,
            "b_name": "3 Phase Socket Outlet:Standard:349046",
            "b_type": "IfcElectricDistributionPoint",
            "relation_value": "3 Phase Socket Outlet:Standard:349046 (ID:77) is near 3 Phase Socket Outlet:Standard:349141 (ID:11)"
        }
    ]

    # 4) Call the summarisation function
    summaries = summarise_spatial_results(spatial_plan, results, openai)

    # 5) Print the summaries
    print("\nSummaries:")
    for s in summaries:
        print(" -", s)


if __name__ == "__main__":
    test_summarise_spatial_results()