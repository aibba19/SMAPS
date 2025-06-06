import os
from db_utils import get_connection, run_query
from main import load_query


#OLD VERSIONS NOT OPTIMIZED
'''

def get_all_object_ids(exclude_ids=None):
    """
    Returns a list of all object IDs from the room_objects table,
    excluding any IDs specified in the exclude_ids list.
    """
    if exclude_ids is None:
        exclude_ids = []
    conn = get_connection()
    cursor = conn.cursor()
    base_query = "SELECT id FROM room_objects"
    if exclude_ids:
        placeholders = ",".join(["%s"] * len(exclude_ids))
        query = f"{base_query} WHERE id NOT IN ({placeholders})"
        cursor.execute(query, tuple(exclude_ids))
    else:
        cursor.execute(base_query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    # Return a simple list of IDs
    return [row[0] for row in rows]

def on_top_relation(object_x_id, object_y_id, scale_factor):
    """
    Determines the 'on top' relation between two objects using the touches and above_below queries.
    
    An object is considered to be on top of another if:
      - It touches the other object (using touches.sql), and
      - It is above the other object (as determined by above_below.sql).
      
    This function checks both orientations:
      1. First, it checks whether Object X touches Object Y.
         If so, it then calls above_below.sql (with parameters in order) and checks
         if the orientation where Object X is the reference has an above_flag equal to 1.
      2. If the above condition is not met, it checks whether Object Y touches Object X.
         If that touches condition is true, it calls above_below.sql with swapped IDs and
         verifies whether the orientation with Object Y as the reference returns an above_flag of 1.
         
    The function returns a detailed explanation of each step and the resulting conclusion.
    """
    conn = get_connection()
    explanation = []

    # 1. Check if Object X touches Object Y.
    touches_query = load_query('touches.sql')
    touches_results = run_query(conn, touches_query, (object_x_id, object_y_id))
    if touches_results:
        touches_relation, touches_flag = touches_results[0]
    else:
        touches_relation, touches_flag = "No result", 0
    explanation.append(f"Step 1: Checking if Object X (ID={object_x_id}) touches Object Y (ID={object_y_id}): {touches_relation} (flag={touches_flag})")

    # 2. If touches, check orientation where Object X is reference using above_below.
    if touches_flag == 1:
        ab_query = load_query('above_below.sql')
        ab_results = run_query(conn, ab_query, (object_x_id, object_y_id, scale_factor))
        if ab_results:
            # Expecting two rows; the first row corresponds to Orientation: X is reference, Y is target.
            ref_object, target_object, relation_text, above_flag, below_flag = ab_results[0]
            explanation.append(f"Step 2: Orientation (X→Y) above_below result: {relation_text} (above_flag={above_flag}, below_flag={below_flag})")
            if above_flag == 1:
                final_result = f"Conclusion: Object X (ID={object_x_id}) is on top of Object Y (ID={object_y_id})."
                explanation.append(final_result)
                conn.close()
                return "\n".join(explanation)

    # 3. Otherwise, check the reverse: if Object Y touches Object X.
    touches_query_rev = load_query('touches.sql')
    touches_results_rev = run_query(conn, touches_query_rev, (object_y_id, object_x_id))
    if touches_results_rev:
        touches_relation_rev, touches_flag_rev = touches_results_rev[0]
    else:
        touches_relation_rev, touches_flag_rev = "No result", 0
    explanation.append(f"Step 3: Checking if Object Y (ID={object_y_id}) touches Object X (ID={object_x_id}): {touches_relation_rev} (flag={touches_flag_rev})")

    if touches_flag_rev == 1:
        ab_query_rev = load_query('above_below.sql')
        ab_results_rev = run_query(conn, ab_query_rev, (object_y_id, object_x_id, scale_factor))
        if ab_results_rev:
            # In the reversed call, the first row corresponds to Orientation: Y is reference, X is target.
            ref_object_rev, target_object_rev, relation_text_rev, above_flag_rev, below_flag_rev = ab_results_rev[0]
            explanation.append(f"Step 4: Orientation (Y→X) above_below result: {relation_text_rev} (above_flag={above_flag_rev}, below_flag={below_flag_rev})")
            if above_flag_rev == 1:
                final_result = f"Conclusion: Object Y (ID={object_y_id}) is on top of Object X (ID={object_x_id})."
                explanation.append(final_result)
                conn.close()
                return "\n".join(explanation)

    # 4. If neither orientation qualifies, no 'on top' relation is established.
    explanation.append("Conclusion: Neither object is definitively on top of the other based on the 'touches' and 'above' (above_below) criteria.")
    conn.close()
    return "\n".join(explanation)

def leans_on_relation(object2_id, object1_id, scale_factor):
    """
    Determines whether object2 'leans on' object1 using the following logic:
    
    LeansOn(o₂, o₁, Fc) ⇔ 
          Touches(o₂, o₁) ∧ 
          ¬Above(o₂, o₁, Fc) ∧ ¬Below(o₂, o₁, Fc) ∧ 
          ∃ o₃ [Touches(o₂, o₃) ∧ Below(o₃, o₂, Fc)].
    
    The function:
      1. Checks if object2 touches object1 (using touches.sql).
      2. If so, calls above_below.sql with (object2, object1, scale_factor)
         and verifies that both the above_flag and below_flag are 0.
      3. Then it searches among candidate objects (excluding object2 and object1)
         to see if there exists at least one object o₃ such that:
             - Touches(o₂, o₃) is true, and
             - When calling above_below.sql for (o₃, object2, scale_factor),
               the below_flag equals 1 (meaning o₃ is below object2).
               
    Returns a detailed multi-line explanation of each step and the conclusion.
    """
    conn = get_connection()
    explanation = []

    # Step 1: Check if object2 touches object1.
    touches_query = load_query('touches.sql')
    touches_results = run_query(conn, touches_query, (object2_id, object1_id))
    if touches_results:
        touches_relation, touches_flag = touches_results[0]
    else:
        touches_relation, touches_flag = "No result", 0
    explanation.append(f"Step 1: Check Touches(o₂, o₁): Object2 (ID={object2_id}) touches Object1 (ID={object1_id}) result: {touches_relation} (flag={touches_flag})")
    
    if touches_flag != 1:
        explanation.append("Conclusion: Since object2 does not touch object1, LeansOn relation does not hold.")
        conn.close()
        return "\n".join(explanation)
    
    # Step 2: Check if object2 is neither above nor below object1.
    ab_query = load_query('above_below.sql')
    ab_results = run_query(conn, ab_query, (object2_id, object1_id, scale_factor))
    if ab_results:
        # Pick the result for the orientation where object2 is the reference.
        _, _, relation_text, above_flag, below_flag = ab_results[0]
    else:
        relation_text, above_flag, below_flag = "No result", 0, 0
    explanation.append(f"Step 2: Check Above/Below(o₂, o₁): {relation_text} (above_flag={above_flag}, below_flag={below_flag})")
    
    if above_flag == 1 or below_flag == 1:
        explanation.append("Conclusion: Object2 is either above or below object1, hence cannot be interpreted as 'leans on'.")
        conn.close()
        return "\n".join(explanation)
    
    # Step 3: Check for supporting contact from below by another object.
    # We need to find an object o3 such that:
    #   Touches(o₂, o₃) is true  AND  Below(o₃, o₂, scale_factor) is true.
    candidate_ids = get_all_object_ids(exclude_ids=[object2_id, object1_id])
    found_candidate = False
    candidate_explanation = []
    for candidate_id in candidate_ids:
        # Check Touches(o₂, o₃)
        touches_candidate = run_query(conn, touches_query, (object2_id, candidate_id))
        if touches_candidate:
            rel_cand, flag_cand = touches_candidate[0]
        else:
            rel_cand, flag_cand = "No result", 0
        candidate_explanation.append(f"Candidate o₃ (ID={candidate_id}): Touches(o₂, o₃) = {rel_cand} (flag={flag_cand})")
        if flag_cand == 1:
            # Check if candidate is below object2: call above_below with (candidate, object2, scale_factor)
            ab_candidate = run_query(conn, ab_query, (candidate_id, object2_id, scale_factor))
            if ab_candidate:
                _, _, rel_cand_ab, above_flag_cand, below_flag_cand = ab_candidate[0]
            else:
                rel_cand_ab, above_flag_cand, below_flag_cand = "No result", 0, 0
            candidate_explanation.append(f"  Above/Below(o₃, o₂) = {rel_cand_ab} (above_flag={above_flag_cand}, below_flag={below_flag_cand})")
            if below_flag_cand == 1:
                found_candidate = True
                candidate_explanation.append(f"  -> Candidate (ID={candidate_id}) satisfies the support condition (touches and is below o₂).")
                break
    explanation.append("Step 3: Check for support from below via some candidate o₃:")
    explanation.extend(candidate_explanation)
    
    if found_candidate:
        conclusion = f"Conclusion: Object2 (ID={object2_id}) leans on Object1 (ID={object1_id}) because it touches object1, is neither above nor below it, and there is at least one supporting object below it."
    else:
        conclusion = f"Conclusion: No candidate o₃ supports the LeansOn relation for Object2 (ID={object2_id}) and Object1 (ID={object1_id})."
    explanation.append(conclusion)
    
    conn.close()
    return "\n".join(explanation)

def affixed_to_relation(object2_id, object1_id, scale_factor):
    """
    Determines whether object2 is affixed to object1 based on the following:
    
    Touches(o₂, o₁) ∧ ¬Above(o₂, o₁, Fc) ∧ ¬∃ o₃ Touches(o₃, o₂) ⇒ AffixedTo(o₂, o₁, Fc)
    
    This function performs:
      1. Checks if object2 touches object1.
      2. Checks using above_below.sql for (object2, object1, scale_factor)
         that object2 is not above object1 (i.e., above_flag = 0).
      3. Verifies that there is no object o₃ (from among all candidates) that touches object2.
      
    Returns a detailed explanation of the decision process.
    """
    conn = get_connection()
    explanation = []

    # Step 1: Check if object2 touches object1.
    touches_query = load_query('touches.sql')
    touches_results = run_query(conn, touches_query, (object2_id, object1_id))
    if touches_results:
        touches_relation, touches_flag = touches_results[0]
    else:
        touches_relation, touches_flag = "No result", 0
    explanation.append(f"Step 1: Check Touches(o₂, o₁): Object2 (ID={object2_id}) touches Object1 (ID={object1_id}) result: {touches_relation} (flag={touches_flag})")
    
    if touches_flag != 1:
        explanation.append("Conclusion: Since object2 does not touch object1, it cannot be affixed to object1.")
        conn.close()
        return "\n".join(explanation)
    
    # Step 2: Check that object2 is not above object1.
    ab_query = load_query('above_below.sql')
    ab_results = run_query(conn, ab_query, (object2_id, object1_id, scale_factor))
    if ab_results:
        _, _, relation_text, above_flag, _ = ab_results[0]
    else:
        relation_text, above_flag = "No result", 0
    explanation.append(f"Step 2: Check Above(o₂, o₁): {relation_text} (above_flag={above_flag})")
    
    if above_flag == 1:
        explanation.append("Conclusion: Object2 is above Object1 so it cannot be considered affixed to it.")
        conn.close()
        return "\n".join(explanation)
    
    # Step 3: Verify that no other object touches object2.
    candidate_ids = get_all_object_ids(exclude_ids=[object2_id])
    candidate_found = False
    candidate_explanation = []
    for candidate_id in candidate_ids:
        touches_candidate = run_query(conn, touches_query, (candidate_id, object2_id))
        if touches_candidate:
            rel_candidate, flag_candidate = touches_candidate[0]
        else:
            rel_candidate, flag_candidate = "No result", 0
        candidate_explanation.append(f"Candidate o₃ (ID={candidate_id}): Touches(o₃, o₂) = {rel_candidate} (flag={flag_candidate})")
        if flag_candidate == 1:
            candidate_found = True
            candidate_explanation.append(f"  -> Found candidate (ID={candidate_id}) that touches object2.")
            break
    explanation.append("Step 3: Check that no candidate object touches object2:")
    explanation.extend(candidate_explanation)
    
    if candidate_found:
        conclusion = f"Conclusion: Object2 (ID={object2_id}) is NOT affixed to Object1 (ID={object1_id}) because there exists at least one other object supporting object2."
    else:
        conclusion = f"Conclusion: Object2 (ID={object2_id}) is affixed to Object1 (ID={object1_id}) because it touches object1, is not above it, and no other object touches it."
    explanation.append(conclusion)
    
    conn.close()
    return "\n".join(explanation)

'''

def on_top_relation(object_x_id, object_y_id, camera_id, scale_factor):
    """
    Determines whether one object is on top of another by:
      1) checking 3D touches via touches.sql, and
      2) checking “above” via above.sql.
    Returns a multi-line explanation with object IDs.
    """
    relation_flag = 0
    conn = get_connection()
    explanation = []

    # Load our SQL snippets
    touches_sql = load_query('touches.sql')
    above_sql   = load_query('above.sql')

    # Step 1: does X touch Y?
    flag_xy = run_query(conn, touches_sql, (object_x_id, object_y_id))[0][0]
    explanation.append(
        f"Step 1: 3D-touches(oX={object_x_id}, oY={object_y_id}) => flag={flag_xy}"
    )
    if flag_xy:
        # Step 2: if they touch, is X above Y?
        above_row = run_query(
            conn,
            above_sql,
            (object_x_id, object_y_id, camera_id, scale_factor)
        )[0]
        # above_row: [top_z, height, above_threshold, above_flag, relation]
        above_flag = above_row[3]
        relation   = above_row[4]

        explanation.append(
            f"Step 2: above(oX={object_x_id}, oY={object_y_id}) => "
            f"{relation} (above={above_flag})"
        )
        if above_flag:
            explanation.append(
                f"Conclusion: Object X (ID={object_x_id}) is on top of Object Y (ID={object_y_id})."
            )
            relation_flag = 1
            conn.close()
            return relation_flag, "\n".join(explanation)

    # Step 3: does Y touch X?
    flag_yx = run_query(conn, touches_sql, (object_y_id, object_x_id))[0][0]
    explanation.append(
        f"Step 3: 3D-touches(oY={object_y_id}, oX={object_x_id}) => flag={flag_yx}"
    )
    if flag_yx:
        # Step 4: if they touch, is Y above X?
        above_row_rev = run_query(
            conn,
            above_sql,
            (object_y_id, object_x_id, camera_id, scale_factor)
        )[0]
        above_flag_rev = above_row_rev[3]
        relation_rev   = above_row_rev[4]

        explanation.append(
            f"Step 4: above(oY={object_y_id}, oX={object_x_id}) => "
            f"{relation_rev} (above={above_flag_rev})"
        )
        if above_flag_rev:
            explanation.append(
                f"Conclusion: Object Y (ID={object_y_id}) is on top of Object X (ID={object_x_id})."
            )
            relation_flag = 1
            conn.close()
            return relation_flag, "\n".join(explanation)

    # Neither orientation works
    explanation.append(
        "Conclusion: Neither object is on top of the other by the 'touches + above' criteria."
    )
    
    conn.close()
    return relation_flag, "\n".join(explanation)




#OPTIMIZED VERSION
def leans_on_relation(object2_id, object1_id, camera_id, scale_factor):
    """
    LeansOn(o₂, o₁, Fc) ⇔ 
      Touches(o₂, o₁) ∧ 
      ¬Above(o₂, o₁, Fc) ∧ ¬Below(o₂, o₁, Fc) ∧ 
      ∃ o₃ [Touches(o₂, o₃) ∧ Below(o₃, o₂, Fc)].
    Uses touches.sql, above.sql, below.sql, and a single EXISTS for the support‐from‐below check.
    """
    relation_flag = 0
    conn = get_connection()
    explanation = []

    # Load SQL snippets
    touches_sql = load_query('touches.sql')
    above_sql   = load_query('above.sql')
    below_sql   = load_query('below.sql')

    # Step 1: does o₂ touch o₁?
    touches_flag = run_query(conn, touches_sql, (object2_id, object1_id))[0][0]
    explanation.append(
        f"Step 1: Touches(o₂={object2_id}, o₁={object1_id}) => flag={touches_flag}"
    )
    if not touches_flag:
        explanation.append("→ No 3D‐touch; aborting LeansOn.")
        conn.close()
        return relation_flag, "\n".join(explanation)

    # Step 2: ensure o₂ is neither above nor below o₁
    above_row = run_query(
        conn, above_sql, (object2_id, object1_id, camera_id, scale_factor)
    )[0]
    above_flag = above_row[3]
    rel_above  = above_row[4]
    explanation.append(
        f"Step 2a: Above(o₂→o₁) => {rel_above} (above_flag={above_flag})"
    )
    if above_flag:
        explanation.append("→ It is above; cannot lean on.")
        conn.close()
        return relation_flag, "\n".join(explanation)

    below_row = run_query(
        conn, below_sql, (object2_id, object1_id, camera_id, scale_factor)
    )[0]
    below_flag = below_row[3]
    rel_below  = below_row[4]
    explanation.append(
        f"Step 2b: Below(o₂→o₁) => {rel_below} (below_flag={below_flag})"
    )
    if below_flag:
        explanation.append("→ It is below; cannot lean on.")
        conn.close()
        return relation_flag, "\n".join(explanation)

    # Step 3: ∃ o₃ supporting below o₂?
    exists_sql = """
    WITH x AS (
      SELECT bbox
      FROM room_objects
      WHERE id = %s
    ), y AS (
      SELECT bbox
      FROM room_objects
      WHERE id = %s
    )
    SELECT EXISTS(
      SELECT 1
      FROM room_objects AS o3, x, y
      WHERE o3.id NOT IN (%s, %s)
        -- new 3D‐touch test with a 0.1m tolerance
        AND ST_3DDWithin(x.bbox, o3.bbox, 0.1)
        -- require o₃’s top face below o₂’s bottom face
        AND ST_ZMax(o3.bbox) < ST_ZMin(y.bbox)
    )::int
    """
    support_exists = run_query(
        conn,
        exists_sql,
        (
            object2_id,     # x.id
            object2_id,     # y.id for ST_ZMin(y.bbox)
            object2_id,     # o3.id NOT IN (o₂, o₁)
            object1_id
        )
    )[0][0]
    explanation.append(f"Step 3: ∃ o₃ supporting below o₂? => {support_exists}")

    # … Conclusion unchanged …
    if support_exists:
        explanation.append(
            f"Conclusion: Object2 (ID={object2_id}) LEANS ON Object1 (ID={object1_id})."
        )
        relation_flag = 1
    else:
        explanation.append(
            f"Conclusion: No supporting object below o₂ → "
            f"Object2 (ID={object2_id}) does NOT lean on Object1 (ID={object1_id})."
        )
        relation_flag = 0

    conn.close()
    return relation_flag, "\n".join(explanation)




#OPTIMIED VERSION 
def affixed_to_relation(object2_id, object1_id, camera_id, scale_factor):
    """
    AffixedTo(o₂,o₁,Fc) ⇔
      Touches(o₂,o₁) ∧ ¬Above(o₂,o₁,Fc) ∧ ¬∃o₃ Touches(o₃,o₂)
    Uses touches.sql, above.sql, and one EXISTS for the final check.
    """
    relation_flag = 0
    conn = get_connection()
    explanation = []

    # Load reusable SQL
    touches_sql = load_query('touches.sql')  # returns 1/0
    above_sql   = load_query('above.sql')    # returns [top_z, height, above_threshold, above_flag, relation]

    # Step 1: Touch test
    flag_touch = run_query(conn, touches_sql, (object2_id, object1_id))[0][0]
    explanation.append(
        f"Step 1: Touches(o₂={object2_id}, o₁={object1_id}) => flag={flag_touch}"
    )
    if not flag_touch:
        explanation.append("→ Does not touch; cannot be affixed.")
        conn.close()
        return relation_flag, "\n".join(explanation)

    # Step 2: Ensure o₂ is not above o₁
    above_row = run_query(
        conn,
        above_sql,
        (object2_id, object1_id, camera_id, scale_factor)
    )[0]
    above_flag = above_row[3]
    rel_above  = above_row[4]
    explanation.append(
        f"Step 2: Above(o₂→o₁) => {rel_above} (above_flag={above_flag})"
    )
    if above_flag:
        explanation.append("→ It is above; cannot be affixed.")
        conn.close()
        return relation_flag, "\n".join(explanation)

    # Step 3: Verify NO other o₃ touches o₂ using ST_3DDWithin (0.1 m tolerance)
    no_other_sql = """
    WITH x AS (
      SELECT bbox
      FROM room_objects
      WHERE id = %s
    )
    SELECT (
      NOT EXISTS (
        SELECT 1
        FROM room_objects AS o3, x
        WHERE o3.id NOT IN (%s, %s)
          AND ST_3DDWithin(x.bbox, o3.bbox, 0.1)
      )
    )::int
    """
    no_other_flag = run_query(
        conn,
        no_other_sql,
        (object2_id, object2_id, object1_id)
    )[0][0]
    explanation.append(
        f"Step 3: no other o₃ touches o₂? => {no_other_flag}"
    )

    # Conclusion
    if no_other_flag:
        explanation.append(
            f"Conclusion: Object2 (ID={object2_id}) is AFFIXED TO Object1 (ID={object1_id})."
        )
        relation_flag = 1
    else:
        explanation.append(
            f"Conclusion: Object2 (ID={object2_id}) is NOT affixed to Object1 (ID={object1_id}); another object touches it."
        )
        relation_flag = 0

    conn.close()
    return relation_flag, explanation




