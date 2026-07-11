"""Per-database structural hints for the worst-performing BIRD databases.

Injected into the prompt for the 3 databases with lowest accuracy:
  california_schools (40%), thrombosis_prediction (46%), financial (47%)

These hints tell the model about common join keys, column name quirks,
and value formats specific to each database — things that aren't obvious
from the schema alone and cause repeated failures.
"""

DB_HINTS: dict[str, str] = {
    "california_schools": (
        "KEY JOINS: frpm.CDSCode = schools.CDSCode = satscores.cds  (always use these to join)\n"
        "COLUMN NAMES with spaces need backtick quoting: `Free Meal Count (K-12)`, `Enrollment (K-12)`, `Enrollment (Ages 5-17)`\n"
        "satscores columns: cds, sname (school name), AvgScrMath, AvgScrRead, AvgScrWrite\n"
        "frpm columns: CDSCode, `School Name`, `Free Meal Count (K-12)`, `Enrollment (K-12)`, `Charter Funding Type`\n"
        "For percent calculations: CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`"
    ),
    "thrombosis_prediction": (
        "SEX values: 'M' = male, 'F' = female\n"
        "Admission values: '+' = in-patient, '-' = out-patient\n"
        "KEY JOINS: Patient.ID = Laboratory.ID = Examination.ID\n"
        "Age: STRFTIME('%Y', 'now') - STRFTIME('%Y', Birthday)  (larger Birthday = younger patient)\n"
        "For ratio of two groups: use COUNT(CASE WHEN cond THEN 1 END) * 1.0 / COUNT(*) — denominator is ALL rows in the set"
    ),
    "financial": (
        "Date format: 'YYYYMM' string (e.g. '201309' = September 2013) — never use LIKE '2013-%'\n"
        "KEY JOINS: yearmonth.CustomerID = customers.CustomerID = transactions_1k.CustomerID\n"
        "Segment values in customers: 'SME', 'LAM', 'KAM'\n"
        "For consumption totals: SUM(yearmonth.Consumption) grouped by CustomerID and filtered by Date\n"
        "Use IIF(condition, value, 0) or CASE WHEN for conditional aggregation"
    ),
}


def get_db_hint(db_id: str) -> str:
    """Return structural hint string for a database, or '' if none defined."""
    return DB_HINTS.get(db_id, "")
