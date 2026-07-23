# Data Constructor

Local Streamlit app for uploading CSV files, importing them into DuckDB, searching table data, and exporting visible results back to CSV.

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

Uploaded CSV files are stored in `data/raw`. The local DuckDB database is `data/app.duckdb`.
