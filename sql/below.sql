WITH params AS (
  SELECT
    CAST(%s AS INTEGER) AS object_x_id,
    CAST(%s AS INTEGER) AS object_y_id,
    CAST(%s AS INTEGER) AS camera_id,
    CAST(%s AS NUMERIC) AS s
),
-- 1. Camera
cam AS (
  SELECT position, fov
  FROM camera
  WHERE id = (SELECT camera_id FROM params)
),
-- 2. Object X + centroid
obj_x_info AS (
  SELECT id, name, bbox, ST_Centroid(bbox) AS centroid
  FROM room_objects
  WHERE id = (SELECT object_x_id FROM params)
),
-- 3. Align the ray→centroid with +Y
rot AS (
  SELECT ST_Azimuth(cam.position, obj_x_info.centroid) AS rot_angle
  FROM cam, obj_x_info
),
-- 4. Transform X into camera space (translate in XY; Z preserved)
obj_x_trans AS (
  SELECT
    o.id, o.name,
    ST_Rotate(
      ST_Translate(o.bbox, -ST_X(cam.position), -ST_Y(cam.position)),
      rot.rot_angle
    ) AS transformed_geom
  FROM room_objects o
  JOIN params ON o.id = params.object_x_id
  CROSS JOIN cam
  CROSS JOIN rot
),
-- 5. Extract camera-space 2D envelope for X & Y limits
obj_x_bbox AS (
  SELECT
    env2d,
    ST_XMin(env2d) AS minx,
    ST_XMax(env2d) AS maxx,
    ST_YMin(env2d) AS miny,
    ST_YMax(env2d) AS maxy
  FROM (
    SELECT
      transformed_geom,
      ST_Envelope(transformed_geom) AS env2d
    FROM obj_x_trans
  ) sub
),
-- 6. True Z-range of X in world-space
obj_x_world_z AS (
  SELECT
    ST_ZMin(bbox) AS bottom_z,
    ST_ZMax(bbox) AS top_z
  FROM obj_x_info
),
-- 7. Compute “below” half-space parameters (extrude downward), extending X-range and Y-range by a small thresold
obj_x_metrics AS (
  SELECT
    wz.bottom_z                                     AS bottom_z,
    (wz.top_z - wz.bottom_z)                        AS height,
    (wz.bottom_z - params.s * (wz.top_z - wz.bottom_z)) AS below_threshold,
    fx.minx,
    fx.maxx,
    fx.miny,
    fx.maxy,
    (fx.minx - 0.5)                                 AS minx_ext,
    (fx.maxx + 0.5)                                 AS maxx_ext,
    (fx.miny - 0.5)                                 AS miny_ext,
    (fx.maxy + 0.5)                                 AS maxy_ext
  FROM obj_x_bbox fx
  CROSS JOIN obj_x_world_z wz
  CROSS JOIN params
),
-- 8. Transform Y into camera-space & dump 3D points
obj_y_points AS (
  SELECT dp.geom AS pt
  FROM (
    SELECT
      ST_Rotate(
        ST_Translate(o.bbox, -ST_X(cam.position), -ST_Y(cam.position)),
        rot.rot_angle
      ) AS transformed_geom
    FROM room_objects o
    JOIN params ON o.id = params.object_y_id
    CROSS JOIN cam
    CROSS JOIN rot
  ) sub
  CROSS JOIN LATERAL ST_DumpPoints(sub.transformed_geom) AS dp
),
-- 9. Flag “below” if ANY point of Y lies in that downward-extruded prism:
--      Z ∈ [below_threshold, bottom_z]
--  AND X ∈ [minx_ext, maxx_ext]
--  AND Y ∈ [miny_ext, maxy_ext]
flag AS (
  SELECT
    MAX(
      CASE
        WHEN ST_Z(pt) BETWEEN (SELECT below_threshold FROM obj_x_metrics)
                         AND (SELECT bottom_z       FROM obj_x_metrics)
         AND ST_X(pt) BETWEEN (SELECT minx_ext       FROM obj_x_metrics)
                         AND (SELECT maxx_ext       FROM obj_x_metrics)
         AND ST_Y(pt) BETWEEN (SELECT miny_ext       FROM obj_x_metrics)
                         AND (SELECT maxy_ext       FROM obj_x_metrics)
        THEN 1 ELSE 0
      END
    ) AS below_flag
  FROM obj_y_points
)
-- 10. Final output with IDs
SELECT
  (SELECT bottom_z          FROM obj_x_metrics) AS obj_x_bottom_z_camera,
  (SELECT height            FROM obj_x_metrics) AS obj_x_height,
  (SELECT below_threshold   FROM obj_x_metrics) AS halfspace_threshold_below_camera,
  flag.below_flag,
  CASE
    WHEN flag.below_flag = 1 THEN
      'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
      || ' (ID:' || (SELECT object_y_id FROM params) || ') is below object '
      || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
      || ' (ID:' || (SELECT object_x_id FROM params) || ')'
    ELSE
      'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
      || ' (ID:' || (SELECT object_y_id FROM params) || ') is NOT below object '
      || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
      || ' (ID:' || (SELECT object_x_id FROM params) || ')'
  END AS relation
FROM flag;
