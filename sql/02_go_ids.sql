CREATE TEMP TABLE go_ids AS
SELECT vacancy_id
FROM raw
WHERE role = 'Программист, разработчик'
  AND regexp_matches(lname, '(^|[^a-zа-я])(go|golang)([^a-zа-я]|$)');