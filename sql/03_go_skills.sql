CREATE TEMP TABLE go_skills AS
SELECT DISTINCT vacancy_id, lower(trim(s)) AS skill
FROM (
    SELECT r.vacancy_id,
           unnest(CASE WHEN strpos(r.key_skills, ';') > 0 THEN string_split(r.key_skills, ';')
                       ELSE string_split(r.key_skills, ',') END) AS s
    FROM raw r
    WHERE r.key_skills IS NOT NULL AND r.vacancy_id IN (SELECT vacancy_id FROM go_ids)
)
WHERE trim(s) <> '';