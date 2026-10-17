import pytest

from kap.sqlguard import SQLRejected, validate_readonly, with_row_cap


@pytest.mark.parametrize("sql", [
    "SELECT 1", "select count(*) from \"case\"", "WITH x AS (SELECT 1) SELECT * FROM x", "  SELECT 1;  ",
    "SELECT * FROM dispatch WHERE outcome = 'delete me'",  # keyword inside a string literal
    "SELECT * FROM part OFFSET 10", "-- comment\nSELECT 1",
])
def test_accepts_readonly(sql):
    assert validate_readonly(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM inventory", "drop table dispatch", "SELECT 1; DELETE FROM part", "UPDATE part SET unit_cost_usd = 0",
    "INSERT INTO part VALUES (1)", "SELECT pg_sleep(10)", "CREATE TABLE x (a int)", "", "   ", "TRUNCATE part",
    "copy part to '/tmp/x'", "SELECT 1 /* */; DROP TABLE part", "GRANT ALL ON part TO public",
    "WITH x AS (DELETE FROM part RETURNING *) SELECT * FROM x", "SELECT lo_import('/etc/passwd')",
])
def test_rejects_everything_else(sql):
    with pytest.raises(SQLRejected):
        validate_readonly(sql)


def test_row_cap_wraps():
    assert with_row_cap("SELECT 1", 5).endswith("LIMIT 5")
