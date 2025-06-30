import csv

LIMIT_DATE = '2025-01-08'
RESULT_TYPE = "('Finish', 'Halfway')"
BUG_TYPE = "('Vulnerability')"
COUNT = """
SELECT project_name, COUNT(*) AS frequency
FROM projects
GROUP BY project_name
ORDER BY frequency DESC;
"""

def SAME_DATE_BUILD_ISSUE(targets):
    target_str = "','".join(targets)
    return (
        "WITH matched_buildlogs AS (\n"
        "    SELECT \n"
        "        i.number,\n"
        "        i.project,\n"
        "        i.rts,\n"
        "        bd.timecreated AS buildlog_timecreated,\n"
        "        bd.build_type,\n"
        "        bd.result,\n"
        "        bd.name AS buildlog_name,\n"
        "        bd.modules AS modules,\n"
        "        bd.revisions AS revisions,\n"
        "        ROW_NUMBER() OVER (\n"
        "            PARTITION BY i.number\n"
        "            ORDER BY bd.timecreated DESC\n"
        "        ) AS rn\n"
        "    FROM issues i\n"
        "    JOIN buildlog_data bd\n"
        "        ON i.project = bd.project\n"
        "        AND i.rts > bd.timecreated\n"
        "        AND bd.build_type = 'Fuzzing'\n"
        f"        AND bd.result IN {RESULT_TYPE}\n"
        f"        AND DATE(bd.timecreated) < '{LIMIT_DATE}'\n"
        "    WHERE i.status IN ('Fixed','Fixed (Verified)')\n"
        
        # f"AND i.type IN {BUG_TYPE}\n"
        f"    AND i.project IN ('{target_str}')\n"
        ")\n"
        "SELECT \n"
        "    number,\n"
        "    project,\n"
        "    rts,\n"
        "    buildlog_timecreated,\n"
        "    build_type,\n"
        "    result,\n"
        "    buildlog_name,\n"
        "    modules,\n"
        "    revisions\n"
        "FROM matched_buildlogs\n"
        "WHERE rn = 1\n"
        "ORDER BY project ASC, rts ASC;\n"
    )

def SUCCESSED_FUZZING_BUILD(project):
    return (
        "SELECT name, timecreated\n"
        "FROM buildlog_data\n"
        f"WHERE project = '{project}'\n"
        "    AND build_type = 'Fuzzing'\n"
        f"    AND result IN {RESULT_TYPE}\n"
        "ORDER BY timecreated\n"
    )

def GET_VALID_ISSUES(targets):
    target_str = "','".join(targets)
    return (
        "SELECT project, number, rts, crash_type\n"
        "FROM issues\n"
        f"WHERE status IN {RESULT_TYPE}\n"
        f"AND project IN ('{target_str}')\n"
        f"AND DATE(rts) < '{LIMIT_DATE}'\n"
        "ORDER BY project, rts, number;\n"
    )

def GET_COVERAGE_BUILDS(project, timecreated):
    return (
        "SELECT *\n"
        "FROM buildlog_data\n"
        f"WHERE timecreated > '{timecreated}'\n"
        f"AND project = '{project}'\n"
        "AND build_type IN ('Coverage')\n"
        "AND result = 'Finish'\n"
        "ORDER BY timecreated ASC\n"
        "LIMIT 1;\n"
    )

def GET_COVERAGE_BUILDS(project):
    return (
        "SELECT *\n"
        "FROM buildlog_data\n"
        f"WHERE project = '{project}'\n"
        "AND build_type IN ('Coverage')\n"
        "AND result = 'Finish'\n"
        "ORDER BY timecreated ASC\n"
    )

def GET_SEVERITY_ISSUES(severity, targets):
    target_str = "','".join(targets)
    return (
        "SELECT project, rts, regressed_build, severity\n"
        "FROM issues\n"
        f"WHERE project IN ('{target_str}')\n"
        f"  AND DATE(rts) < '{LIMIT_DATE}'\n"
        f"  AND severity = '{severity}'\n"
        "  AND EXISTS (\n"
        "    SELECT 1\n"
        "    FROM unnest(regressed_build) AS b\n"
        "    WHERE b IS NOT NULL\n"
        "  )\n"
        "ORDER BY project, rts, number;\n"
    )

def GET_TOTAL_COVERAGE_EACH_PROJECT(project, export_type):
    return (
        "SELECT covered_line,total_line\n"
        "FROM total_coverage\n"
        f"WHERE project = '{project}'\n"
        f"AND {export_type} is not NULL\n"
        f"AND {export_type} != 0\n"
        f"AND DATE(date) < '{LIMIT_DATE}'\n"
        "ORDER BY date;\n"
    )


# import csv


# LIMIT_DATE = '2025-01-08'
# RESULT_TYPE = "('Finish')"





# COUNT ="""
# SELECT project_name, COUNT(*) AS frequency
# FROM projects
# GROUP BY project_name
# ORDER BY frequency DESC;
# """


# def SAME_DATE_BUILD_ISSUE(targets):
#     return f"""
# WITH matched_buildlogs AS (
#     SELECT 
#         i.number,
#         i.project,
#         i.rts,
#         bd.timecreated AS buildlog_timecreated,
#         bd.build_type,
#         bd.result,
#         bd.name AS buildlog_name,
#         bd.modules AS modules,
#         bd.revisions AS revisions,
#         ROW_NUMBER() OVER (
#             PARTITION BY i.number
#             ORDER BY bd.timecreated DESC
#         ) AS rn
#     FROM issues i
#     JOIN buildlog_data bd
#         ON i.project = bd.project
#         AND i.rts > bd.timecreated
#         AND bd.build_type = 'Fuzzing'
#         AND bd.result IN {RESULT_TYPE}
#         AND DATE(bd.timecreated) < '{LIMIT_DATE}'
#     WHERE i.status IN ('Fixed','Fixed (Verified)')
#     AND i.project IN ('{'\',\''.join(targets)}')
# )
# SELECT 
#     number,
#     project,
#     rts,
#     buildlog_timecreated,
#     build_type,
#     result,
#     buildlog_name,
#     modules,
#     revisions
    
# FROM matched_buildlogs
# WHERE rn = 1
# ORDER BY project ASC, rts ASC;
#     """
    
# def SUCCESSED_FUZZING_BUILD(project):
#     return f"""
# SELECT name, timecreated
# FROM buildlog_data
# WHERE project = '{project}'
#     AND build_type = 'Fuzzing'
#     AND result IN {RESULT_TYPE}
# ORDER BY timecreated
#     """
    

# def GET_VALID_ISSUES(targets):
#     return f"""
#     SELECT project, number, rts, crash_type
#     FROM issues
#     WHERE status IN {RESULT_TYPE}
#     AND project IN ('{'\',\''.join(targets)}')
    
#     AND DATE(rts) < '{LIMIT_DATE}'
#     ORDER BY project, rts, number;
#     """

# def GET_COVERAGE_BUILDS(project, timecreated):
#     return f"""
# SELECT *
# FROM buildlog_data
# WHERE timecreated > '{timecreated}'
# AND project = '{project}'
# AND build_type IN ('Coverage')
# AND result = 'Finish'
# ORDER BY timecreated ASC
# LIMIT 1;
#     """
    
# def GET_COVERAGE_BUILDS(project):
#     return f"""
# SELECT *
# FROM buildlog_data
# WHERE project = '{project}'
# AND build_type IN ('Coverage')
# AND result = 'Finish'
# ORDER BY timecreated ASC
#     """
    
    
# def GET_SEVERITY_ISSUES(severity, targets):
#     return f"""
# SELECT project, rts, regressed_build, severity
# FROM issues
# WHERE project IN ('{'\',\''.join(targets)}')
#   AND DATE(rts) < '{LIMIT_DATE}'
#   AND severity = '{severity}'
#   AND EXISTS (
#     SELECT 1
#     FROM unnest(regressed_build) AS b
#     WHERE b IS NOT NULL
#   )
# ORDER BY project, rts, number;

#     """
    
# def GET_TOTAL_COVERAGE_EACH_PROJECT(project,export_type):
#     return f"""
#     SELECT covered_line,total_line
#     FROM total_coverage
#     WHERE project = '{project}'
#     AND {export_type} is not NULL
#     AND {export_type} != 0
#     AND DATE(date) < '{LIMIT_DATE}'
#     ORDER BY date;
#     """