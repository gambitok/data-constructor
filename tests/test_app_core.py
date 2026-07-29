import tempfile
import unittest
from pathlib import Path

import duckdb
import polars as pl

import app


class AppCoreTests(unittest.TestCase):
    def test_uploaded_filename_is_safe_and_content_addressed(self):
        first = app.safe_uploaded_filename("../Cargo File.csv", b"one")
        second = app.safe_uploaded_filename("../Cargo File.csv", b"two")

        self.assertTrue(first.startswith("cargo_file_"))
        self.assertTrue(first.endswith(".csv"))
        self.assertNotIn("..", first)
        self.assertNotIn("/", first)
        self.assertNotIn("\\", first)
        self.assertNotEqual(first, second)

    def test_uploaded_file_signature_changes_with_content(self):
        first = app.uploaded_file_signature("same.csv", b"one")
        second = app.uploaded_file_signature("same.csv", b"two")

        self.assertNotEqual(first, second)

    def test_type_conversion_diagnostics_reports_values_that_would_become_null(self):
        con = duckdb.connect(":memory:")
        con.execute("CREATE TABLE sample(value VARCHAR)")
        con.execute("INSERT INTO sample VALUES ('1'), ('bad'), (NULL)")

        diagnostics = app.get_type_conversion_diagnostics(con, "sample", "value", "INTEGER")

        self.assertEqual(diagnostics["lost_value_count"], 1)
        self.assertEqual(diagnostics["sample_lost_values"]["value"].tolist(), ["bad"])

    def test_delete_foreign_key_preserves_data_and_other_relationships(self):
        db_path = Path(tempfile.gettempdir()) / "data_constructor_unittest.duckdb"
        db_path.unlink(missing_ok=True)
        con = duckdb.connect(str(db_path))
        try:
            app.create_table_from_schema(
                con,
                pl.DataFrame({"id": [1, 2]}),
                "contracts",
                [
                    {
                        "include": True,
                        "source_column": "id",
                        "column_name": "id",
                        "data_type": "INTEGER",
                        "primary_key": True,
                    }
                ],
            )
            app.create_table_from_schema(
                con,
                pl.DataFrame({"id": [10, 11], "contract_id": [1, 2]}),
                "cargo",
                [
                    {
                        "include": True,
                        "source_column": "id",
                        "column_name": "id",
                        "data_type": "INTEGER",
                        "primary_key": True,
                    },
                    {
                        "include": True,
                        "source_column": "contract_id",
                        "column_name": "contract_id",
                        "data_type": "INTEGER",
                        "primary_key": False,
                    },
                ],
            )
            app.create_table_from_schema(
                con,
                pl.DataFrame({"id": [100, 101], "cargo_id": [10, 11]}),
                "equipments",
                [
                    {
                        "include": True,
                        "source_column": "id",
                        "column_name": "id",
                        "data_type": "INTEGER",
                        "primary_key": True,
                    },
                    {
                        "include": True,
                        "source_column": "cargo_id",
                        "column_name": "cargo_id",
                        "data_type": "INTEGER",
                        "primary_key": False,
                    },
                ],
            )
            app.create_sql_foreign_key_relationship(
                con, "cargo", "contract_id", "contracts", "id", "many-to-one"
            )
            app.create_sql_foreign_key_relationship(
                con, "equipments", "cargo_id", "cargo", "id", "many-to-one"
            )

            app.delete_sql_foreign_key_relationship(con, "cargo", "contract_id", "contracts", "id")

            relationships = app.get_relationships(con)
            self.assertEqual(len(relationships), 1)
            self.assertEqual(str(relationships.iloc[0]["from_table"]), "equipments")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM cargo").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM equipments").fetchone()[0], 2)
        finally:
            con.close()
            db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
