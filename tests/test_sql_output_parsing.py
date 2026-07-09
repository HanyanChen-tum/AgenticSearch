from src.rlm.parser import extract_final
from shared.sql_executor import normalize_sql_text


def test_extract_final_preserves_escaped_sql_quotes_and_newlines():
    response = 'FINAL("SELECT AVG(\\"Consumption\\")\\nFROM yearmonth")'

    assert extract_final(response) == 'SELECT AVG("Consumption")\nFROM yearmonth'


def test_normalize_sql_text_unescapes_common_llm_artifacts():
    sql = 'SELECT SUM(Consumption)\\nFROM yearmonth\\nWHERE CustomerID = 6'

    assert normalize_sql_text(sql) == (
        "SELECT SUM(Consumption)\n"
        "FROM yearmonth\n"
        "WHERE CustomerID = 6"
    )
