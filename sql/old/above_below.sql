WITH params AS (
  SELECT 
    CAST(%s AS INTEGER) AS object_x_id,     -- reference
    CAST(%s AS INTEGER) AS object_y_id,     -- target
    CAST(%s AS NUMERIC) AS s                -- scale factor
),
-- 1. Load object X and compute its envelope + Z‐range
obj_x AS (
  SELECT
    o.id,
    o.name,
    o.bbox,
    p.s,
    ST_XMin(env) AS x_min,
    ST_XMax(env) AS x_max,
    ST_YMin(env) AS y_min,
    ST_YMax(env) AS y_max,
    ST_ZMin(o.bbox) AS z_min,
    ST_ZMax(o.bbox) AS z_max
  FROM room_objects o
  JOIN params p ON o.id = p.object_x_id
  CROSS JOIN LATERAL (SELECT ST_Envelope(o.bbox) AS env) sub
),
-- 2. Compute the two Z‐thresholds (above & below) and carry X/Y extents
obj_x_metrics AS (
  SELECT
    x_min, x_max, y_min, y_max, z_min, z_max,
    (z_max + s * (z_max - z_min)) AS above_thresh,
    (z_min - s * (z_max - z_min)) AS below_thresh
  FROM obj_x
),
-- 3. Dump all 3D points of object Y
obj_y_points AS (
  SELECT dp.geom AS pt
  FROM room_objects o
  JOIN params p        ON o.id = p.object_y_id
  CROSS JOIN LATERAL ST_DumpPoints(o.bbox) AS dp
),
-- 4. For each point, test if it falls in the “above” prism OR the “below” prism
flags AS (
  SELECT
    MAX(
      CASE 
        WHEN ST_Z(pt) BETWEEN m.z_max      AND m.above_thresh
         AND ST_X(pt) BETWEEN m.x_min      AND m.x_max
         AND ST_Y(pt) BETWEEN m.y_min      AND m.y_max
        THEN 1 ELSE 0 END
    ) AS above_flag,
    MAX(
      CASE 
        WHEN ST_Z(pt) BETWEEN m.below_thresh AND m.z_min
         AND ST_X(pt) BETWEEN m.x_min        AND m.x_max
         AND ST_Y(pt) BETWEEN m.y_min        AND m.y_max
        THEN 1 ELSE 0 END
    ) AS below_flag
  FROM obj_y_points y
  CROSS JOIN obj_x_metrics m
)
-- 5. Final selector: join names, IDs, flags, and produce a relation string
SELECT
  x.name AS ref_name,
  o.name AS target_name,
  CASE
    WHEN f.above_flag = 1 AND f.below_flag = 1
      THEN x.name || ' (ID:'||x.id||') is both above and below ' 
           || o.name || ' (ID:'||o.id||')'
    WHEN f.above_flag = 1
      THEN x.name || ' (ID:'||x.id||') is above ' 
           || o.name || ' (ID:'||o.id||')'
    WHEN f.below_flag = 1
      THEN x.name || ' (ID:'||x.id||') is below ' 
           || o.name || ' (ID:'||o.id||')'
    ELSE x.name || ' (ID:'||x.id||') is neither above nor below ' 
         || o.name || ' (ID:'||o.id||')'
  END AS relation,
  f.above_flag,
  f.below_flag
FROM obj_x AS x
JOIN room_objects o ON o.id = (SELECT object_y_id FROM params)
CROSS JOIN flags f;