# Data Constructor

Local Streamlit app for turning CSV and Excel files into editable DuckDB tables.

The app lets you:

- switch the interface between English and Ukrainian;
- switch between light and dark themes;
- upload a CSV or Excel file;
- read Cyrillic text from UTF-8 and Windows-1251 CSV files;
- review an automatically suggested table structure;
- rename columns before import;
- include or remove columns;
- add blank columns;
- edit column data types;
- choose primary key columns during import;
- create or replace a DuckDB table;
- define real DuckDB foreign key relationships between imported tables;
- visualize tables and SQL foreign keys in an ERD-style schema designer;
- query related tables with joins, selected columns, search, sorting, and CSV/Excel export;
- save, apply, and delete related-query templates manually;
- rename, clear, or delete imported tables;
- rename columns, change column data types, and edit primary keys with conversion warnings;
- browse, search, and export table data to CSV or Excel.

## Run locally

```powershell
.\run.ps1
```

Then open:

```text
http://localhost:8501
```

## After git pull on another device

From the project folder, run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run.ps1
```

Uploaded source files are stored in `data/raw`. The local DuckDB database is `data/app.duckdb`.
Saved query templates are stored locally in `data/query_templates.json`.

Interface translations are stored in `locales/translations.json`. Add or edit UI text there instead of editing `app.py`.

## Relationships

Relationships are created as real DuckDB `FOREIGN KEY` constraints. The referenced column is made a `PRIMARY KEY`, so it must be unique and not null. Existing child values must already exist in the referenced parent column.

For `one-to-many`, the app treats the source table as the parent and creates the SQL foreign key in the target table. Use `Check relationship` to preview type mismatches, duplicate parent keys, null parent keys, and missing child references before saving.
