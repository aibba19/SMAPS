import ifcopenshell
import ifcopenshell.geom
import psycopg2
import os

TABLE_NAME = "room_objects"

def init_table(cur):
    # 1) Create table if it doesn't exist, with VARCHAR(200) for each attribute
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id SERIAL PRIMARY KEY,
        ifc_type VARCHAR(200),
        name VARCHAR(200),
        ifc_globalid VARCHAR(200),
        bbox GEOMETRY(MULTIPOLYGONZ,4326)
    );
    """
    cur.execute(create_sql)

    # 2) Alter columns to ensure VARCHAR(200) if table already existed
    alter_statements = [
        f"ALTER TABLE {TABLE_NAME} ALTER COLUMN ifc_type TYPE VARCHAR(200);",
        f"ALTER TABLE {TABLE_NAME} ALTER COLUMN name TYPE VARCHAR(200);",
        f"ALTER TABLE {TABLE_NAME} ALTER COLUMN ifc_globalid TYPE VARCHAR(200);"
    ]
    for stmt in alter_statements:
        try:
            cur.execute(stmt)
        except psycopg2.Error:
            # ignore errors (e.g. column already correct, or missing—shouldn't happen)
            pass

def upsert_element(cur, data):
    # Delete any existing record with same GlobalId
    cur.execute(
        f"DELETE FROM {TABLE_NAME} WHERE ifc_globalid = %s;",
        (data['ifc_globalid'],)
    )

    # Insert new
    insert_sql = f"""
    INSERT INTO {TABLE_NAME} (ifc_type, name, ifc_globalid, bbox)
    VALUES (
      %s, %s, %s,
      ST_CollectionExtract(
        ST_3DMakeBox(
          ST_MakePoint(%s, %s, %s),
          ST_MakePoint(%s, %s, %s)
        ),
        3
      )::geometry(MULTIPOLYGONZ,4326)
    );
    """
    cur.execute(insert_sql, (
        data['ifc_type'],
        data['name'],
        data['ifc_globalid'],
        data['min_x'], data['min_y'], data['min_z'],
        data['max_x'], data['max_y'], data['max_z']
    ))

def extract_and_upload(ifc_path, db_params):
    # Open IFC and set up world‐coords geometry
    ifc = ifcopenshell.open(ifc_path)
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    # Connect & init
    conn = psycopg2.connect(**db_params)
    cur = conn.cursor()
    init_table(cur)

    # Iterate IfcProduct elements
    for elem in ifc.by_type("IfcProduct"):
        if not getattr(elem, 'Representation', None):
            continue
        try:
            shape = ifcopenshell.geom.create_shape(settings, elem)
        except Exception as e:
            print(f"Skip {elem.GlobalId}: geometry error {e}")
            continue

        verts = shape.geometry.verts
        if not verts:
            continue
        coords = [(verts[i], verts[i+1], verts[i+2])
                  for i in range(0, len(verts), 3)]
        xs, ys, zs = zip(*coords)
        bbox = {
            "min_x": min(xs), "max_x": max(xs),
            "min_y": min(ys), "max_y": max(ys),
            "min_z": min(zs), "max_z": max(zs)
        }

        data = {
            "ifc_type": elem.is_a(),
            "name": elem.Name or "Unnamed",
            "ifc_globalid": elem.GlobalId,
            **bbox
        }

        upsert_element(cur, data)

        # Print everything including the full bbox
        print(f"Upserted {data['ifc_globalid']} ({data['name']}) [{data['ifc_type']}]")
        print((
            f"  bbox: min_x={data['min_x']}, max_x={data['max_x']}, "
            f"min_y={data['min_y']}, max_y={data['max_y']}, "
            f"min_z={data['min_z']}, max_z={data['max_z']}"
        ))
        print("-" * 60)

    conn.commit()
    cur.close()
    conn.close()

def main():
    # Path to the IFC file.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ifc_file_path = os.path.join(script_dir, 'Uffici R2M_with forniture_IFC2x3.ifc')
    
    # PostgreSQL connection parameters.
    db_connection_params = {
        "host": "localhost",
        "dbname": "r2m_office",
        "user": "postgres",
        "password": "burnout96",
        "port": 5432  # default PostgreSQL port
    }
    
    extract_and_upload(ifc_file_path, db_connection_params)

if __name__ == '__main__':
    main()
