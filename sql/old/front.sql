-- File: front.sql
-- Parameters:
--   1. object_x_id: The reference object ID (e.g., Main Bed).
--   2. object_y_id: The target object ID (e.g., Main Door).
--   3. camera_id: The camera ID.
--   4. s: The scale factor (e.g., 5 means the halfspace extends 5× the object depth).

WITH params AS (
  SELECT 
    CAST(%s AS INTEGER) AS object_x_id,
    CAST(%s AS INTEGER) AS object_y_id,
    CAST(%s AS INTEGER) AS camera_id,
    CAST(%s AS NUMERIC) AS s
),
-- Retrieve camera information.
cam AS (
  SELECT c.position, c.fov
  FROM camera c, params p
  WHERE c.id = p.camera_id
),
-- Retrieve Object X information and compute its centroid in world space.
obj_x_info AS (
  SELECT 
    o.id, 
    o.name, 
    o.bbox, 
    ST_Centroid(o.bbox) AS centroid
  FROM room_objects o, params p
  WHERE o.id = p.object_x_id
),
-- Compute the rotation angle as the azimuth from the camera to object X’s centroid.
rot AS (
  SELECT ST_Azimuth(cam.position, obj_x_info.centroid) AS rot_angle
  FROM cam, obj_x_info
),
----------------------------------------------------------
-- Transform Object X into the new camera space.
obj_x_trans AS (
  SELECT 
    o.id,
    o.name,
    o.bbox,
    ST_Rotate(
      ST_Translate(ST_Force2D(o.bbox), -ST_X(cam.position), -ST_Y(cam.position)),
      r.rot_angle
    ) AS transformed_geom
  FROM room_objects o, params p, cam, rot r
  WHERE o.id = p.object_x_id
),
----------------------------------------------------------
-- Compute the contextualized bounding box of Object X.
obj_x_bbox AS (
  SELECT 
    ST_Envelope(transformed_geom) AS bbox,
    ST_XMin(ST_Envelope(transformed_geom)) AS minx,
    ST_YMin(ST_Envelope(transformed_geom)) AS miny,
    ST_XMax(ST_Envelope(transformed_geom)) AS maxx,
    ST_YMax(ST_Envelope(transformed_geom)) AS maxy
  FROM obj_x_trans
),
-- Compute metrics for Object X in the new camera space:
-- front_y: the Y coordinate of the front face (minimum Y),
-- back_y: the Y coordinate of the back face (maximum Y),
-- depth: the difference between back_y and front_y,
-- threshold: the halfspace threshold computed by extruding the front face.
obj_x_metrics AS (
  SELECT 
    miny AS front_y,
    maxy AS back_y,
    (maxy - miny) AS depth,
    miny - (p.s * (maxy - miny)) AS threshold,
    bbox
  FROM obj_x_bbox, params p
),
-- Construct the front face line (edge at the minimum Y) of Object X’s contextualized bounding box.
front_face_line AS (
  SELECT 
    ST_MakeLine(
      ST_MakePoint(minx, miny),
      ST_MakePoint(maxx, miny)
    ) AS front_line
  FROM obj_x_bbox
),
----------------------------------------------------------
-- Transform Object Y into the same new camera space.
obj_y_trans AS (
  SELECT
    o.id,
    o.name,
    ST_Rotate(
      ST_Translate(ST_Force2D(o.bbox), -ST_X(cam.position), -ST_Y(cam.position)),
      r.rot_angle
    ) AS transformed_geom
  FROM room_objects o, params p, cam, rot r
  WHERE o.id = p.object_y_id
),
-- Extract all points of Object Y's transformed geometry.
obj_y_points AS (
  SELECT (dp.geom) AS pt
  FROM obj_y_trans, LATERAL ST_DumpPoints(transformed_geom) dp
),
-- Check if any point of Object Y lies in the halfspace defined by [threshold, front_y] in camera space.
flag AS (
  SELECT 
    MAX(CASE 
          WHEN ST_Y(pt) BETWEEN (SELECT threshold FROM obj_x_metrics)
                             AND (SELECT front_y FROM obj_x_metrics)
          THEN 1 ELSE 0 END) AS front_flag
  FROM obj_y_points
),
-- Transform the computed front face line back to the original coordinate system for debugging.
front_line_orig AS (
  SELECT 
    ST_Translate(
      ST_Rotate(f.front_line, -r.rot_angle),
      ST_X(cam.position),
      ST_Y(cam.position)
    ) AS front_line_orig
  FROM front_face_line f, cam, rot r
)
----------------------------------------------------------
-- Final output.
SELECT 
  (SELECT front_y FROM obj_x_metrics) AS obj_x_front_y_camera,
  (SELECT depth FROM obj_x_metrics) AS obj_x_depth,
  (SELECT threshold FROM obj_x_metrics) AS halfspace_threshold_camera,
  front_flag,
  CASE 
    WHEN front_flag = 1 THEN 'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params))
         || ' ID : ' || (SELECT id FROM room_objects WHERE id = (SELECT object_y_id FROM params))
         || ' is in front of object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
		 || ' ID : ' || (SELECT id FROM room_objects WHERE id = (SELECT object_x_id FROM params))
    ELSE 'Object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_y_id FROM params)) 
         || ' ID : ' || (SELECT id FROM room_objects WHERE id = (SELECT object_y_id FROM params)) ||
		 ' is NOT in front of object ' || (SELECT name FROM room_objects WHERE id = (SELECT object_x_id FROM params))
		 || ' ID : ' || (SELECT id FROM room_objects WHERE id = (SELECT object_x_id FROM params))
  END AS relation,
  ST_AsText((SELECT front_line_orig FROM front_line_orig)) AS front_face_original
FROM flag;
