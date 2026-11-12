SELECT a.skill || ' | ' || b.skill AS k, count(*) AS cnt
FROM go_skills a
JOIN go_skills b ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
GROUP BY 1
ORDER BY cnt DESC, k;