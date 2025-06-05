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
-- 3. Compute rotation so ray→centroid → +Y
rot AS (
  SELECT ST_Azimuth(cam.position, obj_x_info.centroid) AS rot_angle
  FROM cam, obj_x_info
),
-- 4. Transform X into camera space (XY only; Z preserved)
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
-- 5. Camera-space 2D envelope for X & Y limits
obj_x_bbox AS (
  SELECT
    env2d,
    ST_XMin(env2d) AS minx,
    ST_XMax(env2d) AS maxx,
    ST_YMin(env2d) AS miny,
    ST_YMax(env2d) AS maxy
  FROM (
    SELECT transformed_geom,
           ST_Envelope(transformed_geom) AS env2d
    FROM obj_x_trans
  ) sub
),
-- 6. True Z-range of X in world-space, extended by a threshold
obj_x_world_z AS (
  SELECT
    ST_ZMin(bbox)        AS w_minz,
    ST_ZMax(bbox)        AS w_maxz,
    ST_ZMin(bbox) - 0.5  AS w_minz_ext,
    ST_ZMax(bbox) + 0.5  AS w_maxz_ext
  FROM obj_x_info
),
-- 7. Compute front-halfspace parameters, extending X-range by a threshold
obj_x_metrics AS (
  SELECT
    fx.miny                                        AS front_y,
    (fx.maxy - fx.miny)                            AS depth,
    (fx.miny - params.s * (fx.maxy - fx.miny))     AS threshold,
    fx.minx                                        AS minx,
    fx.maxx                                        AS maxx,
    (fx.minx - 0.5)                                AS minx_ext,
    (fx.maxx + 0.5)                                AS maxx_ext,
    wz.w_minz_ext,
    wz.w_maxz_ext
  FROM obj_x_bbox fx
  CROSS JOIN params
  CROSS JOIN obj_x_world_z wz
),
-- 8. Transform Y into camera-space & dump its 3D points
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
-- 9. Flag “in front” if ANY point lies in the extended 3D prism:
--      Y ∈ [threshold, front_y]
--  AND X ∈ [minx_ext, maxx_ext]
--  AND Z ∈ [w_minz_ext, w_maxz_ext]
flag AS (
  SELECT
    MAX(
      CASE
        WHEN ST_Y(pt) BETWEEN (SELECT threshold    FROM obj_x_metrics)
                         AND (SELECT front_y      FROM obj_x_metrics)
         AND ST_X(pt) BETWEEN (SELECT minx_ext      FROM obj_x_metrics)
                         AND (SELECT maxx_ext      FROM obj_x_metrics)
         AND ST_Z(pt) BETWEEN (SELECT w_minz_ext     FROM obj_x_metrics)
                         AND (SELECT w_maxz_ext     FROM obj_x_metrics)
        THEN 1 ELSE 0
      END
    ) AS front_flag
  FROM obj_y_points
)
-- 10. Final output with IDs
SELECT
  (SELECT front_y       FROM obj_x_metrics) AS obj_x_front_y_camera,
  (SELECT depth         FROM obj_x_metrics) AS obj_x_depth,
  (SELECT threshold     FROM obj_x_metrics) AS halfspace_threshold_front_camera,
  flag.front_flag,
  CASE
    WHEN flag.front_flag = 1 THEN
      'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
      || ' (ID:' || (SELECT object_y_id FROM params) || ') is in front of object '
      || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
      || ' (ID:' || (SELECT object_x_id FROM params) || ')'
    ELSE
      'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
      || ' (ID:' || (SELECT object_y_id FROM params) || ') is NOT in front of object '
      || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
      || ' (ID:' || (SELECT object_x_id FROM params) || ')'
  END AS relation
FROM flag;
