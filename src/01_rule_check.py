import common

con = common.duckdb_connect()
con.execute("""
CREATE TEMP TABLE raw AS
SELECT vacancy_id, name, lower(name) AS lname, role, area, key_skills, salary_from, salary_to, currency
FROM read_csv('%s', header = true, quote = '"', escape = '"', all_varchar = true)
""" % common.CSV_URI)

RX = r"(^|[^a-zа-я])(go|golang)([^a-zа-я]|$)"
RX_SKILL = r"(^|[^a-zа-я0-9_-])(go|golang)([^a-zа-я0-9_-]|$)"
ROLE = "role = 'Программист, разработчик'"
HOMO = "replace(lname, chr(1086), 'o')"


def one(sql):
    return con.execute(sql).fetchone()[0]


def rows(sql):
    return con.execute(sql).fetchall()


total = one("SELECT count(*) FROM raw")
n_role = one("SELECT count(*) FROM raw WHERE " + ROLE)
n_like = one("SELECT count(*) FROM raw WHERE %s AND lname LIKE '%%go%%'" % ROLE)
n_rx = one("SELECT count(*) FROM raw WHERE %s AND regexp_matches(lname, '%s')" % (ROLE, RX))
n_homo = one("SELECT count(*) FROM raw WHERE %s AND regexp_matches(%s, '%s')" % (ROLE, HOMO, RX))
n_all_roles = one("SELECT count(*) FROM raw WHERE regexp_matches(%s, '%s')" % (HOMO, RX))
n_skill_only = one("SELECT count(*) FROM raw WHERE %s AND NOT regexp_matches(%s, '%s') "
                   "AND regexp_matches(lower(key_skills), '%s')" % (ROLE, HOMO, RX, RX_SKILL))

print("Записей в CSV: %d" % total)
print("\n| Условие | Вакансий |")
print("| role = «Программист, разработчик» | %d |" % n_role)
print("| из них 'go' в названии (простой LIKE '%%go%%') | %d |" % n_like)
print("| из них go/golang целым словом (регулярное выражение) | %d |" % n_rx)
print("| есть в простом условии, нет в регулярном (Django, MongoDB, Google...) | %d |" % (n_like - n_rx))
print("| добавляет замена кириллической «о» на латинскую (GО) | %d |" % (n_homo - n_rx))
print("| ИТОГО вакансий варианта (role + название) | %d |" % n_homo)
print("| то же правило без ограничения по role (для справки) | %d |" % n_all_roles)
print("| Go есть только в навыках, не в названии (в вариант не входят) | %d |" % n_skill_only)

print("\nЛожные срабатывания простого LIKE (топ-15 названий):")
for nm, c in rows("SELECT name, count(*) c FROM raw WHERE %s AND lname LIKE '%%go%%' "
                  "AND NOT regexp_matches(%s, '%s') GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 15" % (ROLE, HOMO, RX)):
    print("  %3d  %s" % (c, nm))

print("\nДобавлено заменой кириллической «о» (примеры, repr показывает юникод):")
for (nm,) in rows("SELECT DISTINCT name FROM raw WHERE %s AND regexp_matches(%s, '%s') "
                  "AND NOT regexp_matches(lname, '%s') LIMIT 10" % (ROLE, HOMO, RX, RX)):
    print("  ", ascii(nm))

print("\nПримеры названий Go-вакансий варианта (топ-15):")
for nm, c in rows("SELECT name, count(*) c FROM raw WHERE %s AND regexp_matches(%s, '%s') "
                  "GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 15" % (ROLE, HOMO, RX)):
    print("  %3d  %s" % (c, nm))

print("\nПримеры названий, где Go только в навыках (не входят в вариант):")
for (nm,) in rows("SELECT name FROM raw WHERE %s AND NOT regexp_matches(%s, '%s') "
                  "AND regexp_matches(lower(key_skills), '%s') LIMIT 10" % (ROLE, HOMO, RX, RX_SKILL)):
    print("  ", nm)

d = rows("""
WITH g AS (SELECT * FROM raw WHERE %s AND regexp_matches(%s, '%s'))
SELECT count(*),
       count(*) FILTER (WHERE key_skills IS NOT NULL AND key_skills <> ''),
       count(*) FILTER (WHERE currency = 'RUR' AND (salary_from IS NOT NULL OR salary_to IS NOT NULL))
FROM g""" % (ROLE, HOMO, RX))[0]
print("\nВакансий варианта: %d; с непустым key_skills (участвуют в подсчёте навыков): %d; с зарплатой в RUR: %d" % d)