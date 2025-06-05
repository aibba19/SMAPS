WITH params AS (
  SELECT
    CAST(%s  AS INTEGER) AS object_x_id,       
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
-- 3. Rotation so ray→centroid aligns with +Y
rot AS (
  SELECT ST_Azimuth(cam.position, obj_x_info.centroid) AS rot_angle
  FROM cam, obj_x_info
),
-- 4. Transform X into camera space (preserve Z)
obj_x_trans AS (
  SELECT
    o.id, o.name,
    ST_Rotate(
      ST_Translate(o.bbox, -ST_X(cam.position), -ST_Y(cam.position)),
      rot.rot_angle
    ) AS transformed_geom
  FROM room_objects o
  JOIN params    ON o.id = params.object_x_id
  CROSS JOIN cam
  CROSS JOIN rot
),
-- 5. Camera-space envelope for X/Y limits
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
-- 6. True Z-range of X in world-space (extended by ±1)
obj_x_world_z AS (
  SELECT
    ST_ZMin(bbox)        AS w_minz,
    ST_ZMax(bbox)        AS w_maxz,
    ST_ZMin(bbox) - 1  AS w_minz_ext,
    ST_ZMax(bbox) + 1  AS w_maxz_ext
  FROM obj_x_info
),
-- 7. Compute "right" halfspace parameters (Y-range extended by ±1)
obj_x_metrics AS (
  SELECT
    maxx                                           AS right_x,
    (maxx - minx)                                  AS width,
    (maxx + params.s * (maxx - minx))              AS right_threshold,
    miny                                           AS miny,
    maxy                                           AS maxy,
    (miny - 1)                                   AS miny_ext,
    (maxy + 1)                                   AS maxy_ext
  FROM obj_x_bbox
  CROSS JOIN params
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
    JOIN params    ON o.id = params.object_y_id
    CROSS JOIN cam
    CROSS JOIN rot
  ) sub
  CROSS JOIN LATERAL ST_DumpPoints(sub.transformed_geom) AS dp
),
-- 9. Flag "right" if ANY point lies in the extended 3D prism:
--      X ∈ [right_x, right_threshold]
--  AND Y ∈ [miny_ext, maxy_ext]
--  AND Z ∈ [w_minz_ext, w_maxz_ext]
flag AS (
  SELECT
    MAX(
      CASE
        WHEN ST_X(pt) BETWEEN (SELECT right_x         FROM obj_x_metrics)
                         AND (SELECT right_threshold FROM obj_x_metrics)
         AND ST_Y(pt) BETWEEN (SELECT miny_ext       FROM obj_x_metrics)
                         AND (SELECT maxy_ext       FROM obj_x_metrics)
         AND ST_Z(pt) BETWEEN (SELECT w_minz_ext     FROM obj_x_world_z)
                         AND (SELECT w_maxz_ext     FROM obj_x_world_z)
        THEN 1 ELSE 0
      END
    ) AS right_flag
  FROM obj_y_points
)
-- 10. Final output with names & IDs
SELECT
  (SELECT right_x         FROM obj_x_metrics) AS obj_x_right_x_camera,
  (SELECT width           FROM obj_x_metrics) AS obj_x_width,
  (SELECT right_threshold FROM obj_x_metrics) AS halfspace_threshold_right_camera,
  flag.right_flag,
  CASE
    WHEN flag.right_flag = 1 THEN
      'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
      || ' (ID:' || (SELECT object_y_id FROM params) || ') is to the right of object '
      || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
      || ' (ID:' || (SELECT object_x_id FROM params) || ')'
    ELSE
      'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
      || ' (ID:' || (SELECT object_y_id FROM params) || ') is NOT to the right of object '
      || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
      || ' (ID:' || (SELECT object_x_id FROM params) || ')'
  END AS relation
FROM flag;

