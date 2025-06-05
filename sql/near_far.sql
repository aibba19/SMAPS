-- File: near_far.sql
-- Params: 1) object1_id,  2) object2_id,  3) near/far threshold

WITH p AS (
  SELECT
    %s::integer            AS id1,
    %s::integer            AS id2,
    %s::double precision   AS threshold
)
SELECT
  CASE
    WHEN d.dist < p.threshold
      THEN 
        o1.name || ' (ID:' || o1.id || ') is near ' ||
        o2.name || ' (ID:' || o2.id || ')'
    ELSE 
        o1.name || ' (ID:' || o1.id || ') is far from ' ||
        o2.name || ' (ID:' || o2.id || ')'
  END AS relation,
  d.dist       AS distance,
  (d.dist < p.threshold)  AS is_near,
  (d.dist >= p.threshold) AS is_far
FROM p
JOIN room_objects AS o1
  ON o1.id = p.id1
JOIN room_objects AS o2
  ON o2.id = p.id2
CROSS JOIN LATERAL (
  -- compute ST_3DDistance exactly once
  SELECT ST_3DDistance(o1.bbox, o2.bbox) AS dist
) AS d;
