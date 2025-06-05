import os
import json
import openai
from typing import List, Dict
from config import *

# Import the function you want to test
from prompts.evaluate_rule import evaluate_rule

# Make sure your OPENAI_API_KEY is set in the environment
openai.api_key = OPENAI_API_KEY

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

if __name__ == "__main__":
    test_evaluate_rule()