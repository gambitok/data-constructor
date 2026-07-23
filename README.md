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
- create or replace a DuckDB table;
- define relationships between imported tables;
- visualize tables and saved relationships in an ERD-style schema designer;
- rename, clear, or delete imported tables;
- rename columns and change column data types with conversion warnings;
- browse, search, and export table data.

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
