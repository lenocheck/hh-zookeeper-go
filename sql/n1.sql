SELECT skill AS k, count(*) AS cnt
FROM go_skills
GROUP BY 1
ORDER BY cnt DESC, k;