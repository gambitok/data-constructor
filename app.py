import streamlit as st
import duckdb
import polars as pl
from pathlib import Path

DB_PATH = "data/app.duckdb"
RAW_DIR = Path("data/raw")

st.set_page_config(page_title="Local Data Tool", layout="wide")
st.title("Local Data Tool")

con = duckdb.connect(DB_PATH)

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

if uploaded_file:
    file_path = RAW_DIR / uploaded_file.name

    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"Uploaded: {uploaded_file.name}")

    table_name = Path(uploaded_file.name).stem.replace("-", "_").replace(" ", "_")

    df = pl.read_csv(file_path)

    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")

    st.success(f"Imported to DuckDB table: {table_name}")

tables = con.execute("SHOW TABLES").fetchall()

if tables:
    table_names = [t[0] for t in tables]
    selected_table = st.selectbox("Select table", table_names)

    search = st.text_input("Search text")

    columns = con.execute(f"DESCRIBE {selected_table}").fetchdf()["column_name"].tolist()

    query = f"SELECT * FROM {selected_table}"

    if search:
        conditions = [
            f"CAST({col} AS VARCHAR) ILIKE '%{search}%'"
            for col in columns
        ]
        query += " WHERE " + " OR ".join(conditions)

    query += " LIMIT 1000"

    result = con.execute(query).fetchdf()

    st.dataframe(result, use_container_width=True)

    csv = result.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Export visible result to CSV",
        csv,
        f"{selected_table}_export.csv",
        "text/csv"
    )
else:
    st.info("Upload CSV file to start.")