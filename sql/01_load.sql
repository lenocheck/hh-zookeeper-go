CREATE TEMP TABLE raw AS
SELECT vacancy_id, area, replace(lower(name), chr(1086), 'o') AS lname, role, key_skills
FROM read_csv('{csv}', header = true, quote = '"', escape = '"', all_varchar = true);