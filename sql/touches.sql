-- File: touches.sql
-- Params: 1) object1_id,  2) object2_id

WITH x AS (
  SELECT id, name, bbox
  FROM room_objects
  WHERE id = %s
),
y AS (
  SELECT id, name, bbox
  FROM room_objects
  WHERE id = %s
)
SELECT
  (ST_3DDWithin(x.bbox, y.bbox, 0.1))::int AS touches_flag,
  x.name || ' (ID:' || x.id || ') touches ' ||
  y.name || ' (ID:' || y.id || ')'      AS relation
FROM x, y;
