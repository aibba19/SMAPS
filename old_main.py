import os
import sys
from db_utils import get_connection, load_query
from sql.composed_queries import on_top_relation, leans_on_relation, affixed_to_relation

def run_and_print(query_filename, params, description):
    """
    Helper that loads a SQL query from a file, executes it with provided parameters
    and prints the first result with a description.
    """
    conn = get_connection()
    try:
        query = load_query(query_filename)
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        print(f"\n{description}:")
        print(result)
        cursor.close()
    except Exception as e:
        print(f"Error executing {query_filename}: {e}")
    finally:
        conn.close()

def room5_testing():
    """
    Runs the full suite of spatial‐relation tests for Room5 settings:
      - on_top
      - touches, above_below, front, behind, left, right, near_far
      - leans_on, affixed_to
    """
    # Wall IDs available in your dataset:
    # 46 "West Wall", 47 "East Wall", 48 "South Wall", 49 "North Wall"

    # Define test parameters.
    object_x_id = 2          # Example ID for object X
    object_y_id = 8          # Example ID for object Y
    camera_id = 3            # Example camera ID
    scale_factor = 5.0       # Scale factor for spatial halfspaces
    near_far_threshold = 1.0 # Distance threshold for near/far

    print("===== Testing Composed On-Top Relation =====")
    print(on_top_relation(object_x_id, object_y_id, scale_factor))

    print("\n===== Testing Individual SQL Queries =====")
    run_and_print("touches.sql", (object_x_id, object_y_id), "Touches Relation")

    conn = get_connection()
    try:
        query = load_query("above_below.sql")
        cursor = conn.cursor()
        cursor.execute(query, (object_x_id, object_y_id, scale_factor))
        print("\nAbove/Below Relation (Both Orientations):")
        for row in cursor.fetchall():
            print(row)
        cursor.close()
    except Exception as e:
        print("Error executing above_below.sql:", e)
    finally:
        conn.close()

    run_and_print("front.sql", (object_x_id, object_y_id, camera_id, scale_factor), "Front Relation (X→Y)")
    run_and_print("front.sql", (object_y_id, object_x_id, camera_id, scale_factor), "Front Relation (Y→X)")

    run_and_print("behind.sql", (object_x_id, object_y_id, camera_id, scale_factor), "Behind Relation (X→Y)")
    run_and_print("behind.sql", (object_y_id, object_x_id, camera_id, scale_factor), "Behind Relation (Y→X)")

    run_and_print("left.sql", (object_x_id, object_y_id, camera_id, scale_factor), "Left Relation (X→Y)")
    run_and_print("left.sql", (object_y_id, object_x_id, camera_id, scale_factor), "Left Relation (Y→X)")

    run_and_print("right.sql", (object_x_id, object_y_id, camera_id, scale_factor), "Right Relation (X→Y)")
    run_and_print("right.sql", (object_y_id, object_x_id, camera_id, scale_factor), "Right Relation (Y→X)")

    run_and_print("near_far.sql", (object_x_id, object_y_id, near_far_threshold), "Near/Far Relation")

    # Composed: LeansOn & AffixedTo using a wall (e.g. North Wall ID=49) and candidate ID=12
    wall_id = 49
    candidate_id = 12

    print("\n===== Testing Composed Relation: Leans On =====")
    print(leans_on_relation(candidate_id, wall_id, scale_factor))

    print("\n===== Testing Composed Relation: Affixed To =====")
    print(affixed_to_relation(candidate_id, wall_id, scale_factor))


def generate_near_lists(threshold, output_file="near_lists.txt"):
    """
    For every IFC element in room_objects, find all others that are 'near' it
    (using near_far.sql with the given threshold), and write a text file
    listing, for each element, the set of near elements with their distances.
    """
    conn = get_connection()
    cursor = conn.cursor()
    # 1) Fetch all objects: id, type, name
    cursor.execute("SELECT id, ifc_type, name FROM room_objects")
    objects = cursor.fetchall()  # [(id, type, name), ...]
    cursor.close()

    # Preload the near_far query text
    near_query = load_query("near_far.sql")

    # Prepare a mapping from (id, type, name) to list of near entries
    near_map = {
        (obj_id, obj_type, obj_name): []
        for obj_id, obj_type, obj_name in objects
    }

    # 2) For each pair, call near_far.sql
    for obj_id, obj_type, obj_name in objects:
        for other_id, other_type, other_name in objects:
            if other_id == obj_id:
                continue
            # run near_far.sql: returns [(relation, distance)]
            rows = run_query(conn, near_query, (obj_id, other_id, threshold))
            if not rows:
                continue
            relation, dist = rows[0]
            # relation is like "A is near B" or "A is far from B"
            if relation.endswith(f" is near {other_name}"):
                near_map[(obj_id, obj_type, obj_name)].append(
                    (other_id, other_type, other_name, dist)
                )

    # 3) Write out the text file
    with open(output_file, "w", encoding="utf-8") as f:
        for (obj_id, obj_type, obj_name), near_list in near_map.items():
            f.write(f"{obj_type} {obj_name} (ID={obj_id}):\n")
            if near_list:
                for nid, ntype, nname, dist in near_list:
                    f.write(f"  - {ntype} {nname} (ID={nid}), distance={dist}\n")
            else:
                f.write("  (no near elements)\n")
            f.write("\n")

    conn.close()
    print(f"Near-lists written to {os.path.abspath(output_file)}")

def generate_element_spatial_report(
    threshold, camera_id, scale_factor,
    output_file="spatial_report.txt"
):
    """
    For every IFC element of type IfcBuildingElementProxy, IfcDoor or IfcFurnishingElement,
    finds all ‘near’ neighbors under the given threshold and computes every spatial relation
    (on-top, touches, above/below, front, behind, left, right, leans_on, affixed_to)
    from the reference toward each near element. Writes a human-readable text file.
    """
    conn = get_connection()
    cur = conn.cursor()
    # 1) fetch only the three IFC types
    cur.execute("""
      SELECT id, ifc_type, name
        FROM room_objects
       WHERE ifc_type IN (
         'IfcBuildingElementProxy',
         'IfcDoor',
         'IfcFurnishingElement'
       )
    """)
    objects = cur.fetchall()  # [(id, type, name), ...]
    cur.close()

    # preload SQL filenames
    near_sql        = "near_far.sql"
    touches_sql     = "touches.sql"
    above_below_sql = "above_below.sql"
    front_sql       = "front.sql"
    behind_sql      = "behind.sql"
    left_sql        = "left.sql"
    right_sql       = "right.sql"

    # redirect prints into file
    with open(output_file, "w", encoding="utf-8") as f:
        orig_stdout = sys.stdout
        sys.stdout = f

        # header
        print("Spatial Relations Report")
        print(f"Near/Far threshold: {threshold}")
        print(f"Camera ID: {camera_id}")
        print(f"Scale factor: {scale_factor}")
        print("="*50)
        print()

        for ref_id, ref_type, ref_name in objects:
            print(f"{ref_type} {ref_name} (ID={ref_id}):")
            # find near neighbors
            near_neighbors = []
            for other_id, other_type, other_name in objects:
                if other_id == ref_id:
                    continue
                # near/far
                conn2 = get_connection()
                cur2 = conn2.cursor()
                cur2.execute(load_query(near_sql), (ref_id, other_id, threshold))
                nf = cur2.fetchone()
                cur2.close()
                conn2.close()
                if nf and " is near " in nf[0]:
                    near_neighbors.append((other_id, other_type, other_name, nf[1]))

            if not near_neighbors:
                print("  (no near elements)\n")
                continue

            for other_id, other_type, other_name, dist in near_neighbors:
                print(f"  → Near neighbor: {other_type} {other_name} (ID={other_id}), distance={dist}")
                # On-Top
                print("    On-Top Relation:")
                print(on_top_relation(ref_id, other_id, scale_factor).replace("\n", "\n      "))
                # Touches
                run_and_print(touches_sql, (ref_id, other_id), f"    Touches(o_ref→o_near)")
                # Above/Below (both orientations)
                run_and_print(above_below_sql, (ref_id, other_id, scale_factor), "    AboveBelow (ref→near)")
                run_and_print(above_below_sql, (other_id, ref_id, scale_factor), "    AboveBelow (near→ref)")
                # Front
                run_and_print(front_sql,   (ref_id, other_id, camera_id, scale_factor), "    Front (ref→near)")
                run_and_print(front_sql,   (other_id, ref_id, camera_id, scale_factor), "    Front (near→ref)")
                # Behind
                run_and_print(behind_sql,  (ref_id, other_id, camera_id, scale_factor), "    Behind (ref→near)")
                run_and_print(behind_sql,  (other_id, ref_id, camera_id, scale_factor), "    Behind (near→ref)")
                # Left
                run_and_print(left_sql,    (ref_id, other_id, camera_id, scale_factor), "    Left (ref→near)")
                run_and_print(left_sql,    (other_id, ref_id, camera_id, scale_factor), "    Left (near→ref)")
                # Right
                run_and_print(right_sql,   (ref_id, other_id, camera_id, scale_factor), "    Right (ref→near)")
                run_and_print(right_sql,   (other_id, ref_id, camera_id, scale_factor), "    Right (near→ref)")
                # Composed
                print("    LeansOn Relation:")
                print("      " + leans_on_relation(other_id, ref_id, scale_factor).replace("\n", "\n      "))
                print("    AffixedTo Relation:")
                print("      " + affixed_to_relation(other_id, ref_id, scale_factor).replace("\n", "\n      "))
                print()

            print()
        sys.stdout = orig_stdout

    conn.close()
    print(f"Report written to {os.path.abspath(output_file)}")


def main():
    # First, run Room5 tests
    #room5_testing()

    #generate_near_lists(1)

    generate_element_spatial_report(
    threshold=1.0,
    camera_id=1,
    scale_factor=5.0,
    output_file="r2m_spatial_report.txt"
    )


if __name__ == "__main__":
    main()


