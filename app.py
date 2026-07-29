import json
import logging
import re
import uuid
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path

import duckdb
import pandas as pd
import polars as pl
import streamlit as st
import streamlit.components.v1 as components


DB_PATH = "data/app.duckdb"
RAW_DIR = Path("data/raw")
LOG_PATH = Path("data/app.log")
QUERY_TEMPLATES_PATH = Path("data/query_templates.json")
CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1251", "windows-1251"]
SUPPORTED_TYPES = ["VARCHAR", "INTEGER", "BIGINT", "DOUBLE", "BOOLEAN", "DATE", "TIMESTAMP"]
LANGUAGE_CODES = ["en", "uk"]
THEME_OPTIONS = ["light", "dark"]
SORT_DIRECTIONS = ["asc", "desc"]
TRANSLATIONS_PATH = Path("locales/translations.json")
EXCEL_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def load_translations() -> dict:
    with TRANSLATIONS_PATH.open("r", encoding="utf-8") as translations_file:
        return json.load(translations_file)


TRANSLATIONS = load_translations()

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def get_language() -> str:
    return st.session_state.get("language", "en")


def get_theme() -> str:
    return st.session_state.get("theme", "light")


def t(key: str, **kwargs) -> str:
    language = get_language()
    text = TRANSLATIONS.get(language, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
    return text.format(**kwargs)


def theme_label(theme: str) -> str:
    return t("dark_theme") if theme == "dark" else t("light_theme")


def sort_direction_label(direction: str) -> str:
    return t("descending") if direction == "desc" else t("ascending")


def language_label(language_code: str) -> str:
    return TRANSLATIONS.get(language_code, {}).get("language_name", language_code)


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data")
    return output.getvalue()


def render_export_buttons(df: pd.DataFrame, filename_base: str) -> None:
    csv_column, excel_column = st.columns(2)
    csv = df.to_csv(index=False).encode("utf-8")
    csv_column.download_button(
        t("export_csv"),
        csv,
        f"{filename_base}.csv",
        "text/csv",
        key=f"export_csv_{filename_base}",
    )
    excel_column.download_button(
        t("export_excel"),
        dataframe_to_excel_bytes(df),
        f"{filename_base}.xlsx",
        EXCEL_MIME_TYPE,
        key=f"export_excel_{filename_base}",
    )


def load_query_templates() -> list[dict]:
    if not QUERY_TEMPLATES_PATH.exists():
        return []
    try:
        with QUERY_TEMPLATES_PATH.open("r", encoding="utf-8") as templates_file:
            templates = json.load(templates_file)
    except Exception:
        logging.exception("Failed to load query templates")
        return []
    return templates if isinstance(templates, list) else []


def save_query_templates(templates: list[dict]) -> None:
    QUERY_TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QUERY_TEMPLATES_PATH.open("w", encoding="utf-8") as templates_file:
        json.dump(templates, templates_file, ensure_ascii=False, indent=2)


def column_refs_from_labels(
    labels: list[str],
    column_options: dict[str, tuple[str, str]],
) -> list[dict]:
    return [
        {"table": column_options[label][0], "column": column_options[label][1]}
        for label in labels
        if label in column_options
    ]


def labels_from_column_refs(refs: list[dict], available_labels: list[str]) -> list[str]:
    labels = []
    for ref in refs:
        label = f"{ref.get('table')}.{ref.get('column')}"
        if label in available_labels:
            labels.append(label)
    return labels


def normalize_row_limit(value: object) -> int:
    try:
        row_limit = int(value)
    except (TypeError, ValueError):
        return 1000
    return min(10000, max(1, row_limit))


def make_query_template(
    name: str,
    base_table: str,
    selected_related_tables: list[str],
    selected_column_labels: list[str],
    search_text: str,
    search_column_labels: list[str],
    sort_label: str,
    sort_direction: str,
    row_limit: int,
    column_options: dict[str, tuple[str, str]],
    query: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    sort_columns = column_refs_from_labels([sort_label], column_options) if sort_label else []
    return {
        "id": uuid.uuid4().hex,
        "name": name.strip(),
        "base_table": base_table,
        "related_tables": selected_related_tables,
        "result_columns": column_refs_from_labels(selected_column_labels, column_options),
        "search_text": search_text,
        "search_columns": column_refs_from_labels(search_column_labels, column_options),
        "sort_column": sort_columns[0] if sort_columns else None,
        "sort_direction": sort_direction,
        "row_limit": row_limit,
        "sql": query,
        "created_at": now,
        "updated_at": now,
    }


def upsert_query_template(template: dict) -> None:
    templates = load_query_templates()
    existing_index = next(
        (
            index
            for index, existing_template in enumerate(templates)
            if existing_template.get("name") == template["name"]
        ),
        None,
    )
    if existing_index is None:
        templates.append(template)
    else:
        template["id"] = templates[existing_index].get("id", template["id"])
        template["created_at"] = templates[existing_index].get("created_at", template["created_at"])
        templates[existing_index] = template
    save_query_templates(templates)


def delete_query_template(template_id: str) -> None:
    templates = [
        template
        for template in load_query_templates()
        if template.get("id") != template_id
    ]
    save_query_templates(templates)


def render_query_template_manager(tables: list[str]) -> dict | None:
    templates = load_query_templates()

    with st.expander(t("saved_query_templates")):
        if not templates:
            st.caption(t("no_saved_query_templates"))
            return None

        summary_rows = [
            {
                "name": template.get("name", ""),
                "base_table": template.get("base_table", ""),
                "related_tables": len(template.get("related_tables", [])),
                "result_columns": len(template.get("result_columns", [])),
                "updated_at": template.get("updated_at", ""),
            }
            for template in templates
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        template_options = {
            f"{template.get('name', '')} ({template.get('base_table', '')})": template
            for template in templates
        }
        selected_template_label = st.selectbox(
            t("query_template"),
            list(template_options.keys()),
            key="query_template_select",
        )
        selected_template = template_options[selected_template_label]

        if selected_template.get("sql"):
            st.code(selected_template["sql"], language="sql")

        apply_column, delete_column = st.columns(2)
        if apply_column.button(t("apply_query_template"), key="apply_query_template"):
            if selected_template.get("base_table") not in tables:
                st.error(t("query_template_missing_base", table=selected_template.get("base_table", "")))
                return None
            st.success(t("query_template_applied", name=selected_template.get("name", "")))
            return selected_template

        if delete_column.button(t("delete_query_template"), key="delete_query_template"):
            delete_query_template(str(selected_template.get("id", "")))
            st.success(t("query_template_deleted", name=selected_template.get("name", "")))
            st.rerun()

    return None


def apply_runtime_theme() -> None:
    dark = get_theme() == "dark"
    colors = {
        "background": "#0f172a" if dark else "#ffffff",
        "secondary": "#111827" if dark else "#f8fafc",
        "surface": "#1f2937" if dark else "#ffffff",
        "text": "#e5e7eb" if dark else "#111827",
        "muted": "#9ca3af" if dark else "#64748b",
        "border": "#374151" if dark else "#d1d5db",
        "input": "#111827" if dark else "#ffffff",
    }
    st.markdown(
        f"""
        <style>
            .stApp {{
                background: {colors["background"]};
                color: {colors["text"]};
            }}
            [data-testid="stSidebar"] {{
                background: {colors["secondary"]};
            }}
            [data-testid="stHeader"] {{
                background: {colors["background"]};
            }}
            div[data-testid="stExpander"],
            div[data-testid="stDataFrame"],
            div[data-testid="stDataEditor"] {{
                border-color: {colors["border"]};
            }}
            .stTextInput input,
            .stSelectbox div[data-baseweb="select"] > div {{
                background-color: {colors["input"]};
                color: {colors["text"]};
                border-color: {colors["border"]};
            }}
            p, label, span, h1, h2, h3, h4, h5, h6 {{
                color: {colors["text"]};
            }}
            small, .stCaptionContainer {{
                color: {colors["muted"]};
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_identifier(value: str, fallback: str = "column") -> str:
    name = re.sub(r"\W+", "_", value.strip().lower())
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = fallback
    if name[0].isdigit():
        name = f"{fallback}_{name}"
    return name


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def unique_identifier(base: str, used: set[str]) -> str:
    name = base
    index = 2
    while name in used:
        name = f"{base}_{index}"
        index += 1
    used.add(name)
    return name


def suggest_duckdb_type(dtype: pl.DataType) -> str:
    if dtype in (pl.Int8, pl.Int16, pl.Int32):
        return "INTEGER"
    if dtype in (pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        return "BIGINT"
    if dtype in (pl.Float32, pl.Float64):
        return "DOUBLE"
    if dtype == pl.Boolean:
        return "BOOLEAN"
    if dtype == pl.Date:
        return "DATE"
    if dtype == pl.Datetime:
        return "TIMESTAMP"
    return "VARCHAR"


def make_schema_proposal(df: pl.DataFrame) -> list[dict]:
    used: set[str] = set()
    proposal = []

    for column, dtype in zip(df.columns, df.dtypes):
        suggested_name = unique_identifier(normalize_identifier(column), used)
        source_name = str(column).strip().lower()
        is_index_column = source_name in {"index", "(index)", "unnamed: 0"} or suggested_name in {
            "index",
            "unnamed_0",
        }
        proposal.append(
            {
                "include": not is_index_column,
                "source_column": column,
                "column_name": suggested_name,
                "data_type": suggest_duckdb_type(dtype),
                "primary_key": suggested_name == "id",
            }
        )

    return proposal


def normalize_pandas_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(column) for column in df.columns]

    for column in df.columns:
        if df[column].dtype == "object":
            df[column] = df[column].astype("string")

    return df


def load_uploaded_data(file_path: Path) -> tuple[pl.DataFrame, str]:
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        last_error = None
        for encoding in CSV_ENCODINGS:
            try:
                pandas_df = normalize_pandas_frame(pd.read_csv(file_path, encoding=encoding))
                return pl.from_pandas(pandas_df), f"CSV encoding: {encoding}"
            except UnicodeDecodeError as exc:
                last_error = exc

        raise ValueError(
            "Could not read CSV encoding. Save the file as UTF-8 or Windows-1251 and try again."
        ) from last_error

    if suffix in {".xlsx", ".xlsm"}:
        pandas_df = normalize_pandas_frame(pd.read_excel(file_path, engine="openpyxl"))
        return pl.from_pandas(pandas_df), "Excel workbook"

    raise ValueError(t("unsupported_file_type"))


def table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    return bool(
        con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        ).fetchone()[0]
    )


def cleanup_rebuild_tables(con: duckdb.DuckDBPyConnection) -> None:
    rebuild_tables = [
        row[0]
        for row in con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
                AND table_name LIKE 'app_rebuild_%'
            ORDER BY table_name DESC
            """
        ).fetchall()
    ]

    remaining = set(rebuild_tables)
    while remaining:
        dropped_in_pass = set()
        for table_name in sorted(remaining, reverse=True):
            try:
                con.execute(f"DROP TABLE {quote_identifier(table_name)}")
                dropped_in_pass.add(table_name)
            except Exception:
                logging.exception("Failed to drop rebuild table: %s", table_name)

        remaining -= dropped_in_pass
        if not dropped_in_pass:
            raise ValueError(
                "Could not clean temporary rebuild tables: "
                + ", ".join(sorted(remaining))
            )


def list_user_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("SHOW TABLES").fetchall()
    return sorted([row[0] for row in rows if not row[0].startswith("app_")])


def get_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> list[str]:
    return con.execute(f"DESCRIBE {quote_identifier(table_name)}").fetchdf()["column_name"].tolist()


def get_table_schema(con: duckdb.DuckDBPyConnection, table_name: str) -> pd.DataFrame:
    return con.execute(f"DESCRIBE {quote_identifier(table_name)}").fetchdf()


def get_relationships(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT DISTINCT
            fk.constraint_name AS id,
            fk_cols.table_name AS from_table,
            fk_cols.column_name AS from_column,
            'foreign key' AS relationship_type,
            pk_cols.table_name AS to_table,
            pk_cols.column_name AS to_column,
            NULL::TIMESTAMP AS created_at
        FROM information_schema.referential_constraints fk
        JOIN information_schema.key_column_usage fk_cols
            ON fk.constraint_catalog = fk_cols.constraint_catalog
            AND fk.constraint_schema = fk_cols.constraint_schema
            AND fk.constraint_name = fk_cols.constraint_name
        JOIN information_schema.key_column_usage pk_cols
            ON fk.unique_constraint_catalog = pk_cols.constraint_catalog
            AND fk.unique_constraint_schema = pk_cols.constraint_schema
            AND fk.unique_constraint_name = pk_cols.constraint_name
            AND fk_cols.position_in_unique_constraint = pk_cols.ordinal_position
        ORDER BY from_table, from_column, to_table, to_column
        """
    ).fetchdf()


def get_column_type(con: duckdb.DuckDBPyConnection, table_name: str, column_name: str) -> str:
    schema = get_table_schema(con, table_name)
    matches = schema[schema["column_name"] == column_name]
    if matches.empty:
        raise ValueError(f"Column not found: {table_name}.{column_name}")
    return str(matches.iloc[0]["column_type"])


def relationship_edges(relationships: pd.DataFrame) -> list[dict]:
    return dataframe_relationship_rows(relationships)


def get_reachable_tables(base_table: str, relationships: pd.DataFrame) -> dict[str, list[dict]]:
    edges = relationship_edges(relationships)
    paths: dict[str, list[dict]] = {base_table: []}
    queue = [base_table]

    while queue:
        table = queue.pop(0)
        for edge in edges:
            if edge["from_table"] == table:
                next_table = edge["to_table"]
            elif edge["to_table"] == table:
                next_table = edge["from_table"]
            else:
                continue

            if next_table in paths:
                continue

            paths[next_table] = paths[table] + [edge]
            queue.append(next_table)

    return paths


def make_column_options(con: duckdb.DuckDBPyConnection, tables: list[str]) -> dict[str, tuple[str, str]]:
    options = {}
    for table in tables:
        for column in get_columns(con, table):
            options[f"{table}.{column}"] = (table, column)
    return options


def build_related_query(
    selected_columns: list[tuple[str, str]],
    base_table: str,
    selected_related_tables: list[str],
    paths: dict[str, list[dict]],
    search_text: str,
    search_columns: list[tuple[str, str]],
    sort_column: tuple[str, str] | None,
    sort_direction: str,
    row_limit: int,
) -> tuple[str, list[str]]:
    tables_to_join = [base_table] + selected_related_tables
    aliases = {base_table: "t0"}
    alias_index = 1
    join_edges = []
    seen_edges = set()

    for table in selected_related_tables:
        for edge in paths.get(table, []):
            edge_key = (
                edge["from_table"],
                edge["from_column"],
                edge["to_table"],
                edge["to_column"],
            )
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                join_edges.append(edge)

    join_clauses = []
    pending = join_edges.copy()
    while pending:
        progressed = False
        for edge in pending.copy():
            child_table = edge["from_table"]
            parent_table = edge["to_table"]
            child_alias = aliases.get(child_table)
            parent_alias = aliases.get(parent_table)

            if child_alias and not parent_alias:
                parent_alias = f"t{alias_index}"
                alias_index += 1
                aliases[parent_table] = parent_alias
                join_clauses.append(
                    f"LEFT JOIN {quote_identifier(parent_table)} {parent_alias} "
                    f"ON {child_alias}.{quote_identifier(edge['from_column'])} = "
                    f"{parent_alias}.{quote_identifier(edge['to_column'])}"
                )
                pending.remove(edge)
                progressed = True
            elif parent_alias and not child_alias:
                child_alias = f"t{alias_index}"
                alias_index += 1
                aliases[child_table] = child_alias
                join_clauses.append(
                    f"LEFT JOIN {quote_identifier(child_table)} {child_alias} "
                    f"ON {child_alias}.{quote_identifier(edge['from_column'])} = "
                    f"{parent_alias}.{quote_identifier(edge['to_column'])}"
                )
                pending.remove(edge)
                progressed = True
            elif child_alias and parent_alias:
                pending.remove(edge)
                progressed = True

        if not progressed:
            raise ValueError("Could not build join path for selected tables.")

    for table in tables_to_join:
        if table not in aliases:
            aliases[table] = f"t{alias_index}"
            alias_index += 1

    select_sql = ", ".join(
        f"{aliases[table]}.{quote_identifier(column)} AS {quote_identifier(table + '__' + column)}"
        for table, column in selected_columns
    )
    query = f"SELECT {select_sql}\nFROM {quote_identifier(base_table)} {aliases[base_table]}"
    if join_clauses:
        query += "\n" + "\n".join(join_clauses)

    params = []
    if search_text and search_columns:
        conditions = [
            f"CAST({aliases[table]}.{quote_identifier(column)} AS VARCHAR) ILIKE ?"
            for table, column in search_columns
        ]
        query += "\nWHERE " + " OR ".join(conditions)
        params.extend([f"%{search_text}%"] * len(search_columns))

    if sort_column:
        sort_table, sort_col = sort_column
        direction = "DESC" if sort_direction == "desc" else "ASC"
        query += f"\nORDER BY {aliases[sort_table]}.{quote_identifier(sort_col)} {direction}"

    query += "\nLIMIT ?"
    params.append(row_limit)
    return query, params


def get_primary_key_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> list[str]:
    rows = con.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_name = ?
        ORDER BY kcu.ordinal_position
        """,
        [table_name],
    ).fetchall()
    return [row[0] for row in rows]


def ensure_primary_key(con: duckdb.DuckDBPyConnection, table_name: str, column_name: str) -> None:
    primary_key_columns = get_primary_key_columns(con, table_name)
    if primary_key_columns == [column_name]:
        return
    if primary_key_columns:
        raise ValueError(
            f"{table_name} already has primary key: {', '.join(primary_key_columns)}"
        )

    try:
        con.execute(
            f"ALTER TABLE {quote_identifier(table_name)} ADD PRIMARY KEY ({quote_identifier(column_name)})"
        )
    except Exception as exc:
        raise ValueError(t("parent_pk_failed", table=table_name, column=column_name)) from exc


def validate_relationship_data(
    con: duckdb.DuckDBPyConnection,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> None:
    from_type = get_column_type(con, from_table, from_column)
    to_type = get_column_type(con, to_table, to_column)
    if from_type != to_type:
        raise ValueError(t("column_type_mismatch", from_type=from_type, to_type=to_type))

    invalid_count = con.execute(
        f"""
        SELECT COUNT(*)
        FROM {quote_identifier(from_table)} child
        WHERE child.{quote_identifier(from_column)} IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                FROM {quote_identifier(to_table)} parent
                WHERE parent.{quote_identifier(to_column)} = child.{quote_identifier(from_column)}
            )
        """
    ).fetchone()[0]
    if invalid_count:
        raise ValueError(
            t(
                "referential_integrity_failed",
                count=invalid_count,
                from_table=from_table,
                from_column=from_column,
                to_table=to_table,
                to_column=to_column,
            )
        )


def relationship_exists(
    relationships: pd.DataFrame,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> bool:
    if relationships.empty:
        return False
    matches = relationships[
        (relationships["from_table"] == from_table)
        & (relationships["from_column"] == from_column)
        & (relationships["to_table"] == to_table)
        & (relationships["to_column"] == to_column)
    ]
    return not matches.empty


def format_relationship_label(relationship: dict) -> str:
    return (
        f"{relationship['from_table']}.{relationship['from_column']} -> "
        f"{relationship['to_table']}.{relationship['to_column']}"
    )


def resolve_sql_fk_direction(
    source_table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    relationship_type: str,
) -> tuple[str, str, str, str]:
    if relationship_type == "many-to-many":
        raise ValueError(t("many_to_many_requires_junction"))
    if relationship_type == "one-to-many":
        return target_table, target_column, source_table, source_column
    return source_table, source_column, target_table, target_column


def get_relationship_diagnostics(
    con: duckdb.DuckDBPyConnection,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> dict:
    child_type = get_column_type(con, child_table, child_column)
    parent_type = get_column_type(con, parent_table, parent_column)
    parent_null_count = con.execute(
        f"""
        SELECT COUNT(*)
        FROM {quote_identifier(parent_table)}
        WHERE {quote_identifier(parent_column)} IS NULL
        """
    ).fetchone()[0]
    parent_duplicate_count = con.execute(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {quote_identifier(parent_column)}
            FROM {quote_identifier(parent_table)}
            WHERE {quote_identifier(parent_column)} IS NOT NULL
            GROUP BY {quote_identifier(parent_column)}
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    orphan_count = con.execute(
        f"""
        SELECT COUNT(*)
        FROM {quote_identifier(child_table)} child
        WHERE child.{quote_identifier(child_column)} IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                FROM {quote_identifier(parent_table)} parent
                WHERE parent.{quote_identifier(parent_column)} = child.{quote_identifier(child_column)}
            )
        """
    ).fetchone()[0]
    sample_orphans = con.execute(
        f"""
        SELECT DISTINCT child.{quote_identifier(child_column)} AS missing_value
        FROM {quote_identifier(child_table)} child
        WHERE child.{quote_identifier(child_column)} IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                FROM {quote_identifier(parent_table)} parent
                WHERE parent.{quote_identifier(parent_column)} = child.{quote_identifier(child_column)}
            )
        LIMIT 20
        """
    ).fetchdf()
    return {
        "child_type": child_type,
        "parent_type": parent_type,
        "parent_null_count": parent_null_count,
        "parent_duplicate_count": parent_duplicate_count,
        "orphan_count": orphan_count,
        "sample_orphans": sample_orphans,
    }


def build_table_constraint_definitions(
    primary_key_columns: list[str],
    foreign_key_rows: list[dict],
) -> list[str]:
    definitions = []
    if primary_key_columns:
        definitions.append(
            "PRIMARY KEY ("
            + ", ".join(quote_identifier(column) for column in primary_key_columns)
            + ")"
        )
    definitions.extend(
        (
            f"FOREIGN KEY ({quote_identifier(row['from_column'])}) "
            f"REFERENCES {quote_identifier(row['to_table'])} ({quote_identifier(row['to_column'])})"
        )
        for row in foreign_key_rows
    )
    return definitions


def remap_relationship_rows_for_table(
    relationship_rows: list[dict],
    table_name: str,
    column_renames: dict[str, str] | None = None,
) -> list[dict]:
    if column_renames is None:
        column_renames = {}

    remapped_rows = []
    for relationship in relationship_rows:
        remapped = relationship.copy()
        if remapped["from_table"] == table_name:
            remapped["from_column"] = column_renames.get(
                remapped["from_column"],
                remapped["from_column"],
            )
        if remapped["to_table"] == table_name:
            remapped["to_column"] = column_renames.get(
                remapped["to_column"],
                remapped["to_column"],
            )
        remapped_rows.append(remapped)
    return remapped_rows


def validate_relationship_columns_for_rebuild(
    table_name: str,
    column_names: list[str],
    relationship_rows: list[dict],
) -> None:
    available_columns = set(column_names)
    missing_columns = sorted(
        {
            relationship["from_column"]
            for relationship in relationship_rows
            if relationship["from_table"] == table_name
            and relationship["from_column"] not in available_columns
        }
        | {
            relationship["to_column"]
            for relationship in relationship_rows
            if relationship["to_table"] == table_name
            and relationship["to_column"] not in available_columns
        }
    )
    if missing_columns:
        raise ValueError(
            t(
                "relationship_columns_required",
                table=table_name,
                columns=", ".join(missing_columns),
            )
        )


def get_table_foreign_key_rows(con: duckdb.DuckDBPyConnection, table_name: str) -> list[dict]:
    relationships = get_relationships(con)
    return [
        {
            "from_table": str(row["from_table"]),
            "from_column": str(row["from_column"]),
            "to_table": str(row["to_table"]),
            "to_column": str(row["to_column"]),
            "relationship_type": str(row["relationship_type"]),
        }
        for _, row in relationships[relationships["from_table"] == table_name].iterrows()
    ]


def dataframe_relationship_rows(relationships: pd.DataFrame) -> list[dict]:
    if relationships.empty:
        return []
    return [
        {
            "from_table": str(row["from_table"]),
            "from_column": str(row["from_column"]),
            "to_table": str(row["to_table"]),
            "to_column": str(row["to_column"]),
            "relationship_type": str(row["relationship_type"]),
        }
        for _, row in relationships.iterrows()
    ]


def get_referencing_subtree(
    relationships: pd.DataFrame,
    table_name: str,
) -> list[str]:
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(parent_table: str) -> None:
        children = sorted(
            set(
                str(row["from_table"])
                for _, row in relationships[relationships["to_table"] == parent_table].iterrows()
                if str(row["from_table"]) != parent_table
            )
        )
        for child_table in children:
            if child_table in visited:
                continue
            visited.add(child_table)
            visit(child_table)
            ordered.append(child_table)

    visit(table_name)
    return ordered


def rebuild_table_with_constraints(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    primary_key_columns: list[str],
    foreign_key_rows: list[dict] | None = None,
    column_order: list[str] | None = None,
    column_definitions: list[str] | None = None,
    target_columns: list[str] | None = None,
    select_parts: list[str] | None = None,
    source_relation: str | None = None,
    manage_transaction: bool = True,
) -> None:
    schema = get_table_schema(con, table_name)
    temp_table = normalize_identifier(f"app_rebuild_{table_name}_{uuid.uuid4().hex[:8]}", "tmp")
    if foreign_key_rows is None:
        foreign_key_rows = get_table_foreign_key_rows(con, table_name)
    if column_definitions is None and column_order:
        schema = (
            schema.assign(
                sort_order=schema["column_name"].map(
                    {column: index for index, column in enumerate(column_order)}
                )
            )
            .sort_values("sort_order")
            .drop(columns=["sort_order"])
        )
    if target_columns is None:
        target_columns = [
            str(row["column_name"])
            for _, row in schema.iterrows()
        ]
    if column_definitions is None:
        column_definitions = [
            f"{quote_identifier(str(row['column_name']))} {row['column_type']}"
            for _, row in schema.iterrows()
        ]
    if select_parts is None:
        select_parts = [
            quote_identifier(str(row["column_name"]))
            for _, row in schema.iterrows()
        ]
    if source_relation is None:
        source_relation = quote_identifier(table_name)

    constraint_definitions = build_table_constraint_definitions(primary_key_columns, foreign_key_rows)
    columns_sql = ", ".join(
        quote_identifier(column)
        for column in target_columns
    )

    if manage_transaction:
        con.execute("BEGIN")
    try:
        con.execute(
            f"""
            CREATE TABLE {quote_identifier(temp_table)} (
                {", ".join(column_definitions)}
            )
            """
        )
        con.execute(
            f"""
            INSERT INTO {quote_identifier(temp_table)} ({columns_sql})
            SELECT {", ".join(select_parts)}
            FROM {source_relation}
            """
        )
        con.execute(f"DROP TABLE {quote_identifier(table_name)}")
        con.execute(
            f"""
            CREATE TABLE {quote_identifier(table_name)} (
                {", ".join(column_definitions + constraint_definitions)}
            )
            """
        )
        con.execute(
            f"""
            INSERT INTO {quote_identifier(table_name)} ({columns_sql})
            SELECT {columns_sql}
            FROM {quote_identifier(temp_table)}
            """
        )
        con.execute(f"DROP TABLE {quote_identifier(temp_table)}")
        if manage_transaction:
            con.execute("COMMIT")
    except Exception:
        if manage_transaction:
            con.execute("ROLLBACK")
            cleanup_rebuild_tables(con)
        raise


def rebuild_table_preserving_references(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    primary_key_columns: list[str],
    foreign_key_rows: list[dict],
    column_order: list[str] | None = None,
    column_definitions: list[str] | None = None,
    target_columns: list[str] | None = None,
    select_parts: list[str] | None = None,
    source_relation: str | None = None,
    column_renames: dict[str, str] | None = None,
    manage_transaction: bool = True,
) -> None:
    relationships_before = get_relationships(con)
    all_relationship_rows = remap_relationship_rows_for_table(
        dataframe_relationship_rows(relationships_before),
        table_name,
        column_renames,
    )
    all_relationship_rows = [
        row
        for row in all_relationship_rows
        if row["from_table"] != table_name
    ] + foreign_key_rows
    referencing_subtree = get_referencing_subtree(relationships_before, table_name)
    if target_columns is None:
        target_columns = [
            str(row["column_name"])
            for _, row in get_table_schema(con, table_name).iterrows()
        ]
    validate_relationship_columns_for_rebuild(table_name, target_columns, all_relationship_rows)

    if manage_transaction:
        cleanup_rebuild_tables(con)
        con.execute("BEGIN")
    try:
        # Detach deepest children first, so DuckDB allows rebuilding their parents.
        for child_table in referencing_subtree:
            rebuild_table_with_constraints(
                con,
                child_table,
                get_primary_key_columns(con, child_table),
                [],
                manage_transaction=False,
            )

        rebuild_table_with_constraints(
            con,
            table_name,
            primary_key_columns,
            foreign_key_rows,
            column_order,
            column_definitions,
            target_columns,
            select_parts,
            source_relation,
            manage_transaction=False,
        )

        # Restore parents before children, so referenced keys already exist.
        for child_table in reversed(referencing_subtree):
            child_relationships = [
                row for row in all_relationship_rows if row["from_table"] == child_table
            ]
            for relationship in child_relationships:
                validate_relationship_data(
                    con,
                    relationship["from_table"],
                    relationship["from_column"],
                    relationship["to_table"],
                    relationship["to_column"],
                )
                ensure_primary_key(con, relationship["to_table"], relationship["to_column"])
            rebuild_table_with_constraints(
                con,
                child_table,
                get_primary_key_columns(con, child_table),
                child_relationships,
                manage_transaction=False,
            )
        if manage_transaction:
            con.execute("COMMIT")
    except Exception:
        if manage_transaction:
            con.execute("ROLLBACK")
            cleanup_rebuild_tables(con)
        raise


def create_sql_foreign_key_relationship(
    con: duckdb.DuckDBPyConnection,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
    relationship_type: str,
) -> None:
    if from_table == to_table:
        raise ValueError(t("same_table_fk_not_supported"))

    cleanup_rebuild_tables(con)

    relationships = get_relationships(con)
    if relationship_exists(relationships, from_table, from_column, to_table, to_column):
        raise ValueError(t("relationship_exists"))

    validate_relationship_data(con, from_table, from_column, to_table, to_column)
    parent_primary_keys = get_primary_key_columns(con, to_table)
    if parent_primary_keys and parent_primary_keys != [to_column]:
        raise ValueError(
            f"{to_table} already has primary key: {', '.join(parent_primary_keys)}"
        )

    con.execute("BEGIN")
    try:
        if not parent_primary_keys:
            rebuild_table_preserving_references(
                con,
                to_table,
                [to_column],
                get_table_foreign_key_rows(con, to_table),
                manage_transaction=False,
            )

        relationships = get_relationships(con)
        child_relationships = [
            {
                "from_table": str(row["from_table"]),
                "from_column": str(row["from_column"]),
                "to_table": str(row["to_table"]),
                "to_column": str(row["to_column"]),
                "relationship_type": str(row["relationship_type"]),
            }
            for _, row in relationships[relationships["from_table"] == from_table].iterrows()
        ]
        child_relationships.append(
            {
                "from_table": from_table,
                "from_column": from_column,
                "to_table": to_table,
                "to_column": to_column,
                "relationship_type": relationship_type,
            }
        )

        for relationship in child_relationships:
            validate_relationship_data(
                con,
                relationship["from_table"],
                relationship["from_column"],
                relationship["to_table"],
                relationship["to_column"],
            )
            ensure_primary_key(con, relationship["to_table"], relationship["to_column"])

        rebuild_table_preserving_references(
            con,
            from_table,
            get_primary_key_columns(con, from_table),
            child_relationships,
            manage_transaction=False,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        cleanup_rebuild_tables(con)
        raise


def delete_sql_foreign_key_relationship(
    con: duckdb.DuckDBPyConnection,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> None:
    cleanup_rebuild_tables(con)
    relationships = get_relationships(con)
    if not relationship_exists(relationships, from_table, from_column, to_table, to_column):
        raise ValueError(t("relationship_not_found"))

    remaining_foreign_keys = []
    for _, row in relationships[relationships["from_table"] == from_table].iterrows():
        is_selected_relationship = (
            str(row["from_table"]) == from_table
            and str(row["from_column"]) == from_column
            and str(row["to_table"]) == to_table
            and str(row["to_column"]) == to_column
        )
        if is_selected_relationship:
            continue
        remaining_foreign_keys.append(
            {
                "from_table": str(row["from_table"]),
                "from_column": str(row["from_column"]),
                "to_table": str(row["to_table"]),
                "to_column": str(row["to_column"]),
                "relationship_type": str(row["relationship_type"]),
            }
        )

    rebuild_table_preserving_references(
        con,
        from_table,
        get_primary_key_columns(con, from_table),
        remaining_foreign_keys,
    )


def get_related_columns(relationships: pd.DataFrame) -> set[tuple[str, str]]:
    related: set[tuple[str, str]] = set()
    for _, row in relationships.iterrows():
        related.add((str(row["from_table"]), str(row["from_column"])))
        related.add((str(row["to_table"]), str(row["to_column"])))
    return related


def build_schema_designer_html(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    relationships: pd.DataFrame,
) -> str:
    dark = get_theme() == "dark"
    palette = {
        "canvas_bg": "#0f172a" if dark else "#ffffff",
        "grid": "#1f2937" if dark else "#f8fafc",
        "border": "#475569" if dark else "#d1d5db",
        "table_bg": "#111827" if dark else "#ffffff",
        "table_border": "#64748b" if dark else "#94a3b8",
        "header_bg": "#020617" if dark else "#334155",
        "header_border": "#1f2937" if dark else "#1e293b",
        "text": "#e5e7eb" if dark else "#111827",
        "muted": "#94a3b8" if dark else "#64748b",
        "row_border": "#374151" if dark else "#e5e7eb",
        "related_bg": "#1e3a8a" if dark else "#eff6ff",
        "dot": "#64748b" if dark else "#cbd5e1",
        "line": "#60a5fa" if dark else "#2563eb",
        "label_stroke": "#0f172a" if dark else "#ffffff",
    }
    card_width = 340
    card_gap_x = 190
    card_gap_y = 220
    columns_per_row = 3
    header_height = 40
    row_height = 34
    top_lane_base = 28
    top_lane_step = 18
    side_lane_step = 18
    max_gap_lanes = max(int((card_gap_x - 52) / side_lane_step) + 1, 1)
    relationship_count = len(relationships)
    top_margin = 90 + relationship_count * top_lane_step
    related_columns = get_related_columns(relationships)
    table_positions = {}
    table_heights = {}
    table_grid = {}
    column_anchors = {}
    cards = []
    table_schemas = {}
    row_heights = {}

    for index, table in enumerate(tables):
        schema = get_table_schema(con, table)
        row = index // columns_per_row
        height = header_height + max(len(schema), 1) * row_height

        table_schemas[table] = schema
        row_heights[row] = max(row_heights.get(row, 0), height)

    row_offsets = {}
    current_y = top_margin
    for row in range(max(row_heights.keys(), default=-1) + 1):
        row_offsets[row] = current_y
        current_y += row_heights.get(row, 0) + card_gap_y

    for index, table in enumerate(tables):
        schema = table_schemas[table]
        row = index // columns_per_row
        col = index % columns_per_row
        x = 40 + col * (card_width + card_gap_x)
        y = row_offsets[row]
        height = header_height + max(len(schema), 1) * row_height

        table_positions[table] = (x, y)
        table_heights[table] = height
        table_grid[table] = (row, col)

        rows = []
        for column_index, (_, column_row) in enumerate(schema.iterrows()):
            column_name = str(column_row["column_name"])
            column_type = str(column_row["column_type"])
            column_title = f"{column_name}: {column_type}"
            is_related = (table, column_name) in related_columns
            column_y = y + header_height + column_index * row_height + row_height / 2
            column_anchors[(table, column_name)] = {
                "left": (x, column_y),
                "right": (x + card_width, column_y),
            }
            marker = '<span class="key-marker">FK</span>' if is_related else '<span class="dot-marker"></span>'
            rows.append(
                f"""
                <div class="erd-column {'is-related' if is_related else ''}" title="{escape(column_title)}">
                    {marker}
                    <span class="column-name">{escape(column_name)}</span>
                    <span class="column-type">{escape(column_type)}</span>
                </div>
                """
            )

        cards.append(
            f"""
            <section class="erd-table" style="left:{x}px; top:{y}px; width:{card_width}px;">
                <header title="{escape(table)}">{escape(table)}</header>
                <div class="erd-columns">{''.join(rows)}</div>
            </section>
            """
        )

    canvas_width = 40 + columns_per_row * card_width + (columns_per_row - 1) * card_gap_x + 160
    canvas_height = max(current_y + relationship_count * top_lane_step, 420)
    lines = []
    route_lane_counts = {}

    def next_route_lane(key: tuple) -> int:
        lane = route_lane_counts.get(key, 0)
        route_lane_counts[key] = lane + 1
        return lane

    for edge_index, (_, relationship) in enumerate(relationships.iterrows()):
        from_table = str(relationship["from_table"])
        to_table = str(relationship["to_table"])
        from_column = str(relationship["from_column"])
        to_column = str(relationship["to_column"])
        from_anchor = column_anchors.get((from_table, from_column))
        to_anchor = column_anchors.get((to_table, to_column))

        if not from_anchor or not to_anchor:
            continue

        from_x, from_y = table_positions[from_table]
        to_x, to_y = table_positions[to_table]
        from_row, from_col = table_grid[from_table]
        to_row, to_col = table_grid[to_table]
        top_bus_y = top_lane_base + edge_index * top_lane_step
        bottom_bus_y = max(
            from_y + table_heights[from_table],
            to_y + table_heights[to_table],
        ) + 28 + edge_index * top_lane_step
        left_bus_x = 18 + edge_index * side_lane_step
        is_adjacent_same_row = from_row == to_row and abs(from_col - to_col) == 1

        if from_table == to_table:
            lane = next_route_lane(("self", from_table))
            start_x, start_y = from_anchor["right"]
            end_x, end_y = to_anchor["right"]
            loop_x = start_x + 42 + lane * side_lane_step
            path = f"M {start_x} {start_y} L {loop_x} {start_y} L {loop_x} {end_y} L {end_x} {end_y}"
        elif is_adjacent_same_row:
            lane = next_route_lane(("gap", from_row, min(from_col, to_col), max(from_col, to_col)))
            gap_lane = lane % max_gap_lanes
            if from_col < to_col:
                start_x, start_y = from_anchor["right"]
                end_x, end_y = to_anchor["left"]
                lane_x = start_x + 26 + gap_lane * side_lane_step
            else:
                start_x, start_y = from_anchor["left"]
                end_x, end_y = to_anchor["right"]
                lane_x = end_x + 26 + gap_lane * side_lane_step

            if lane >= max_gap_lanes:
                bus_y = top_bus_y
                start_lane_x = lane_x
                end_lane_x = lane_x
                path = (
                    f"M {start_x} {start_y} "
                    f"L {start_lane_x} {start_y} "
                    f"L {start_lane_x} {bus_y} "
                    f"L {end_lane_x} {bus_y} "
                    f"L {end_lane_x} {end_y} "
                    f"L {end_x} {end_y}"
                )
            else:
                path = f"M {start_x} {start_y} L {lane_x} {start_y} L {lane_x} {end_y} L {end_x} {end_y}"
        elif from_col == to_col:
            lane = next_route_lane(("same-col", from_col, min(from_row, to_row), max(from_row, to_row)))
            start_x, start_y = from_anchor["right"]
            end_x, end_y = to_anchor["right"]
            lane_x = start_x + 34 + lane * side_lane_step
            path = (
                f"M {start_x} {start_y} "
                f"L {lane_x} {start_y} "
                f"L {lane_x} {end_y} "
                f"L {end_x} {end_y}"
            )
        elif from_x <= to_x:
            lane = next_route_lane(("top-bottom", min(from_col, to_col), max(from_col, to_col), min(from_row, to_row), max(from_row, to_row)))
            start_x, start_y = from_anchor["right"]
            end_x, end_y = to_anchor["left"]
            bus_y = top_lane_base + lane * top_lane_step if from_row <= to_row else bottom_bus_y
            start_lane_x = start_x + 28
            end_lane_x = end_x - 28
            path = (
                f"M {start_x} {start_y} "
                f"L {start_lane_x} {start_y} "
                f"L {start_lane_x} {bus_y} "
                f"L {end_lane_x} {bus_y} "
                f"L {end_lane_x} {end_y} "
                f"L {end_x} {end_y}"
            )
        else:
            lane = next_route_lane(("top-bottom", min(from_col, to_col), max(from_col, to_col), min(from_row, to_row), max(from_row, to_row)))
            start_x, start_y = from_anchor["left"]
            end_x, end_y = to_anchor["right"]
            bus_y = top_lane_base + lane * top_lane_step if from_row <= to_row else bottom_bus_y
            start_lane_x = max(left_bus_x, start_x - 28)
            end_lane_x = end_x + 28
            path = (
                f"M {start_x} {start_y} "
                f"L {start_lane_x} {start_y} "
                f"L {start_lane_x} {bus_y} "
                f"L {end_lane_x} {bus_y} "
                f"L {end_lane_x} {end_y} "
                f"L {end_x} {end_y}"
            )

        lines.append(
            f"""
            <path d="{path}" />
            <circle cx="{start_x}" cy="{start_y}" r="4"></circle>
            <circle cx="{end_x}" cy="{end_y}" r="4"></circle>
            """
        )

    return f"""
    <style>
        .erd-shell,
        .erd-shell * {{
            box-sizing: border-box;
        }}
        .erd-shell {{
            --erd-canvas-bg: {palette["canvas_bg"]};
            --erd-grid: {palette["grid"]};
            --erd-border: {palette["border"]};
            --erd-table-bg: {palette["table_bg"]};
            --erd-table-border: {palette["table_border"]};
            --erd-header-bg: {palette["header_bg"]};
            --erd-header-border: {palette["header_border"]};
            --erd-text: {palette["text"]};
            --erd-muted: {palette["muted"]};
            --erd-row-border: {palette["row_border"]};
            --erd-related-bg: {palette["related_bg"]};
            --erd-dot: {palette["dot"]};
            --erd-line: {palette["line"]};
            --erd-label-stroke: {palette["label_stroke"]};
            position: relative;
            width: 100%;
            height: 100vh;
            min-height: 680px;
            border: 1px solid var(--erd-border);
            border-radius: 6px;
            overflow: hidden;
            background: var(--erd-canvas-bg);
        }}
        .erd-shell:fullscreen {{
            width: 100vw;
            height: 100vh;
            min-height: 100vh;
            border: 0;
            border-radius: 0;
        }}
        .erd-toolbar {{
            position: absolute;
            top: 12px;
            right: 12px;
            z-index: 5;
            display: flex;
            gap: 8px;
        }}
        .erd-fullscreen-btn {{
            border: 1px solid var(--erd-border);
            background: var(--erd-table-bg);
            color: var(--erd-text);
            border-radius: 4px;
            padding: 7px 10px;
            font: 600 12px Arial, sans-serif;
            cursor: pointer;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.16);
        }}
        .erd-fullscreen-btn:hover {{
            border-color: var(--erd-line);
        }}
        .erd-zoom-value {{
            border: 1px solid var(--erd-border);
            background: var(--erd-table-bg);
            color: var(--erd-text);
            border-radius: 4px;
            padding: 7px 9px;
            font: 600 12px Arial, sans-serif;
            min-width: 54px;
            text-align: center;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.16);
        }}
        .erd-canvas {{
            --erd-canvas-bg: {palette["canvas_bg"]};
            --erd-grid: {palette["grid"]};
            --erd-border: {palette["border"]};
            --erd-table-bg: {palette["table_bg"]};
            --erd-table-border: {palette["table_border"]};
            --erd-header-bg: {palette["header_bg"]};
            --erd-header-border: {palette["header_border"]};
            --erd-text: {palette["text"]};
            --erd-muted: {palette["muted"]};
            --erd-row-border: {palette["row_border"]};
            --erd-related-bg: {palette["related_bg"]};
            --erd-dot: {palette["dot"]};
            --erd-line: {palette["line"]};
            --erd-label-stroke: {palette["label_stroke"]};
            position: relative;
            width: {canvas_width}px;
            height: {canvas_height}px;
            min-width: 100%;
            overflow: auto;
            background:
                linear-gradient(var(--erd-grid) 23px, transparent 24px),
                linear-gradient(90deg, var(--erd-grid) 23px, transparent 24px),
                var(--erd-canvas-bg);
            background-size: 24px 24px;
            font-family: Arial, sans-serif;
            transform-origin: top left;
        }}
        .erd-stage {{
            width: {canvas_width}px;
            height: {canvas_height}px;
        }}
        .erd-shell:fullscreen .erd-canvas {{
            min-width: {canvas_width}px;
            min-height: {canvas_height}px;
        }}
        .erd-lines {{
            position: absolute;
            inset: 0;
            width: {canvas_width}px;
            height: {canvas_height}px;
            pointer-events: none;
        }}
        .erd-lines path {{
            fill: none;
            stroke: var(--erd-line);
            stroke-width: 2;
            marker-end: url(#arrow);
        }}
        .erd-lines circle {{
            fill: var(--erd-canvas-bg);
            stroke: var(--erd-line);
            stroke-width: 2;
        }}
        .erd-table {{
            position: absolute;
            z-index: 2;
            border: 1px solid var(--erd-table-border);
            border-radius: 4px;
            background: var(--erd-table-bg);
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
            overflow: hidden;
        }}
        .erd-table header {{
            background: var(--erd-header-bg);
            color: #ffffff;
            display: flex;
            align-items: center;
            height: {header_height}px;
            font-weight: 700;
            font-size: 13px;
            line-height: 1.2;
            padding: 0 12px;
            border-bottom: 1px solid var(--erd-header-border);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .erd-columns {{
            display: grid;
        }}
        .erd-column {{
            display: grid;
            grid-template-columns: 32px minmax(0, 1fr) max-content;
            align-items: center;
            column-gap: 8px;
            height: {row_height}px;
            min-height: {row_height}px;
            padding: 0 10px;
            border-bottom: 1px solid var(--erd-row-border);
            font-size: 12px;
            line-height: 1.2;
            color: var(--erd-text);
        }}
        .erd-column:last-child {{
            border-bottom: 0;
        }}
        .erd-column.is-related {{
            background: var(--erd-related-bg);
        }}
        .column-name {{
            min-width: 0;
            font-weight: 600;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .column-type {{
            color: var(--erd-muted);
            font-family: Consolas, monospace;
            font-size: 11px;
            white-space: nowrap;
            justify-self: end;
        }}
        .key-marker {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 16px;
            border-radius: 3px;
            background: var(--erd-line);
            color: #ffffff;
            font-size: 9px;
            font-weight: 700;
            flex: 0 0 auto;
        }}
        .dot-marker {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--erd-dot);
            flex: 0 0 auto;
        }}
    </style>
    <div class="erd-shell" id="erd-shell">
        <div class="erd-toolbar">
            <button class="erd-fullscreen-btn" type="button" onclick="setErdZoom(-0.1)">-</button>
            <span class="erd-zoom-value" id="erd-zoom-value">100%</span>
            <button class="erd-fullscreen-btn" type="button" onclick="setErdZoom(0.1)">+</button>
            <button class="erd-fullscreen-btn" type="button" onclick="toggleErdFullscreen()">{escape(t("fullscreen"))}</button>
        </div>
        <div class="erd-stage" id="erd-stage">
            <div class="erd-canvas">
                <svg class="erd-lines" viewBox="0 0 {canvas_width} {canvas_height}">
                    <defs>
                        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="{palette["line"]}"></path>
                        </marker>
                    </defs>
                    {''.join(lines)}
                </svg>
                {''.join(cards)}
            </div>
        </div>
    </div>
    <script>
        let erdZoom = 1;
        function applyErdZoom() {{
            const canvas = document.querySelector('.erd-canvas');
            const stage = document.getElementById('erd-stage');
            const value = document.getElementById('erd-zoom-value');
            canvas.style.transform = `scale(${{erdZoom}})`;
            stage.style.width = `${{{canvas_width} * erdZoom}}px`;
            stage.style.height = `${{{canvas_height} * erdZoom}}px`;
            value.textContent = `${{Math.round(erdZoom * 100)}}%`;
        }}
        function setErdZoom(delta) {{
            erdZoom = Math.min(2, Math.max(0.4, Number((erdZoom + delta).toFixed(2))));
            applyErdZoom();
        }}
        function toggleErdFullscreen() {{
            const shell = document.getElementById('erd-shell');
            if (!document.fullscreenElement) {{
                shell.requestFullscreen();
            }} else {{
                document.exitFullscreen();
            }}
        }}
        applyErdZoom();
    </script>
    """


def create_table_from_schema(
    con: duckdb.DuckDBPyConnection,
    df: pl.DataFrame,
    table_name: str,
    schema_rows: list[dict],
) -> None:
    created_columns, column_definitions, select_parts, primary_key_columns = prepare_schema_creation_parts(schema_rows)

    con.register("uploaded_df", df)
    try:
        if table_exists(con, table_name):
            relationships = dataframe_relationship_rows(get_relationships(con))
            validate_relationship_columns_for_rebuild(table_name, created_columns, relationships)
            required_parent_columns = [
                relationship["to_column"]
                for relationship in relationships
                if relationship["to_table"] == table_name
                and relationship["to_column"] not in primary_key_columns
            ]
            if required_parent_columns:
                primary_key_columns = primary_key_columns + required_parent_columns

            rebuild_table_preserving_references(
                con,
                table_name,
                primary_key_columns,
                [
                    relationship
                    for relationship in relationships
                    if relationship["from_table"] == table_name
                ],
                column_definitions=column_definitions,
                target_columns=created_columns,
                select_parts=select_parts,
                source_relation="uploaded_df",
            )
        else:
            create_new_table_from_select(
                con,
                table_name,
                column_definitions,
                created_columns,
                select_parts,
                "uploaded_df",
                primary_key_columns,
            )
    finally:
        con.unregister("uploaded_df")


def prepare_schema_creation_parts(schema_rows: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    selected_rows = [row for row in schema_rows if row.get("include")]
    if not selected_rows:
        raise ValueError("Select at least one column.")

    used: set[str] = set()
    created_columns = []
    select_parts = []
    column_definitions = []
    primary_key_columns = []
    for row in selected_rows:
        column_name = normalize_identifier(str(row["column_name"]))
        if column_name in used:
            raise ValueError(f"Duplicate column name: {column_name}")
        used.add(column_name)
        created_columns.append(column_name)

        data_type = row["data_type"]
        if data_type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported data type: {data_type}")

        column_definitions.append(f"{quote_identifier(column_name)} {data_type}")
        if row.get("primary_key"):
            primary_key_columns.append(column_name)

        source_column = row.get("source_column")
        if source_column:
            source_sql = quote_identifier(source_column)
        else:
            source_sql = "NULL"

        select_parts.append(
            f"TRY_CAST({source_sql} AS {data_type}) AS {quote_identifier(column_name)}"
        )

    return created_columns, column_definitions, select_parts, primary_key_columns


def create_new_table_from_select(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    column_definitions: list[str],
    target_columns: list[str],
    select_parts: list[str],
    source_relation: str,
    primary_key_columns: list[str],
) -> None:
    constraints = build_table_constraint_definitions(primary_key_columns, [])
    columns_sql = ", ".join(quote_identifier(column) for column in target_columns)
    con.execute("BEGIN")
    try:
        con.execute(
            f"""
            CREATE TABLE {quote_identifier(table_name)} (
                {", ".join(column_definitions + constraints)}
            )
            """
        )
        con.execute(
            f"""
            INSERT INTO {quote_identifier(table_name)} ({columns_sql})
            SELECT {", ".join(select_parts)}
            FROM {source_relation}
            """
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def render_upload_import(con: duckdb.DuckDBPyConnection) -> None:
    st.header(t("create_table_from_file"))

    uploaded_file = st.file_uploader(t("upload_file"), type=["csv", "xlsx", "xlsm"])
    if not uploaded_file:
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    file_path = RAW_DIR / uploaded_file.name
    file_path.write_bytes(uploaded_file.getbuffer())

    try:
        df, source_info = load_uploaded_data(file_path)
    except Exception as exc:
        logging.exception("Failed to load uploaded file: %s", uploaded_file.name)
        st.error(str(exc))
        st.caption(t("details_written", path=LOG_PATH))
        return

    suggested_table_name = normalize_identifier(Path(uploaded_file.name).stem, "table")

    st.caption(source_info)
    st.subheader(t("preview"))
    st.dataframe(df.head(25).to_pandas(), use_container_width=True, hide_index=True)

    table_name = st.text_input(t("table_name"), suggested_table_name)
    table_name = normalize_identifier(table_name, "table")

    if "schema_proposal_file" not in st.session_state or st.session_state.schema_proposal_file != uploaded_file.name:
        st.session_state.schema_proposal_file = uploaded_file.name
        st.session_state.schema_proposal = make_schema_proposal(df)

    st.subheader(t("column_proposal"))
    edited_schema = st.data_editor(
        st.session_state.schema_proposal,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "include": st.column_config.CheckboxColumn(t("include")),
            "source_column": st.column_config.SelectboxColumn(
                t("source_column"),
                options=[""] + df.columns,
                help=t("source_column_help"),
            ),
            "column_name": st.column_config.TextColumn(t("column_name"), required=True),
            "data_type": st.column_config.SelectboxColumn(t("data_type"), options=SUPPORTED_TYPES, required=True),
            "primary_key": st.column_config.CheckboxColumn(t("primary_key"), help=t("primary_key_warning")),
        },
        hide_index=True,
    )
    st.session_state.schema_proposal = edited_schema

    if st.button(t("create_or_replace_table"), type="primary"):
        try:
            create_table_from_schema(con, df, table_name, edited_schema)
            st.success(t("table_created", table=table_name))
        except Exception as exc:
            logging.exception("Failed to create table from uploaded file: %s", uploaded_file.name)
            st.error(str(exc))
            st.caption(t("details_written", path=LOG_PATH))


def render_relationships(con: duckdb.DuckDBPyConnection) -> None:
    tables = list_user_tables(con)
    st.header(t("relationships"))

    if len(tables) < 2:
        st.info(t("need_two_tables"))
        return

    st.info(t("relationship_direction_help"))

    left, right = st.columns(2)
    from_table = left.selectbox(t("from_table"), tables, key="from_table")
    to_table = right.selectbox(t("to_table"), tables, key="to_table")

    from_columns = get_columns(con, from_table)
    to_columns = get_columns(con, to_table)

    rel_left, rel_mid, rel_right = st.columns(3)
    from_column = rel_left.selectbox(t("from_column"), from_columns)
    relationship_type = rel_mid.selectbox(t("relationship"), ["many-to-one", "one-to-one", "one-to-many", "many-to-many"])
    to_column = rel_right.selectbox(t("to_column"), to_columns)

    try:
        child_table, child_column, parent_table, parent_column = resolve_sql_fk_direction(
            from_table,
            from_column,
            to_table,
            to_column,
            relationship_type,
        )
        st.caption(
            t(
                "resolved_fk_direction",
                child_table=child_table,
                child_column=child_column,
                parent_table=parent_table,
                parent_column=parent_column,
            )
        )
    except Exception as exc:
        child_table = child_column = parent_table = parent_column = None
        st.error(str(exc))

    if st.button(t("check_relationship"), disabled=child_table is None):
        try:
            diagnostics = get_relationship_diagnostics(
                con,
                child_table,
                child_column,
                parent_table,
                parent_column,
            )
            st.subheader(t("relationship_check_title"))
            st.dataframe(
                pd.DataFrame(
                    [
                        {"check": "child_type", "value": diagnostics["child_type"]},
                        {"check": "parent_type", "value": diagnostics["parent_type"]},
                        {"check": t("parent_nulls"), "value": diagnostics["parent_null_count"]},
                        {"check": t("parent_duplicates"), "value": diagnostics["parent_duplicate_count"]},
                        {"check": t("orphan_values"), "value": diagnostics["orphan_count"]},
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
            if not diagnostics["sample_orphans"].empty:
                st.caption(t("sample_orphans"))
                st.dataframe(diagnostics["sample_orphans"], use_container_width=True, hide_index=True)
            if (
                diagnostics["child_type"] == diagnostics["parent_type"]
                and diagnostics["parent_null_count"] == 0
                and diagnostics["parent_duplicate_count"] == 0
                and diagnostics["orphan_count"] == 0
            ):
                st.success(t("relationship_check_ok"))
        except Exception as exc:
            logging.exception("Failed to check SQL foreign key relationship")
            st.error(str(exc))

    if st.button(t("save_relationship")):
        try:
            if child_table is None:
                raise ValueError(t("many_to_many_requires_junction"))
            create_sql_foreign_key_relationship(
                con,
                child_table,
                child_column,
                parent_table,
                parent_column,
                relationship_type,
            )
            st.success(t("relationship_real_fk_saved"))
            st.rerun()
        except Exception as exc:
            logging.exception("Failed to create SQL foreign key relationship")
            st.error(str(exc))

    relationships = get_relationships(con).drop(columns=["id"])

    if not relationships.empty:
        st.dataframe(relationships, use_container_width=True, hide_index=True)
        render_delete_relationship(con, relationships)


def render_delete_relationship(con: duckdb.DuckDBPyConnection, relationships: pd.DataFrame) -> None:
    with st.expander(t("delete_relationship")):
        relationship_rows = dataframe_relationship_rows(relationships)
        relationship_options = {
            format_relationship_label(relationship): relationship
            for relationship in relationship_rows
        }
        selected_relationship_label = st.selectbox(
            t("relationship_to_delete"),
            list(relationship_options.keys()),
            key="delete_relationship_select",
        )
        st.caption(t("delete_relationship_caption"))
        delete_confirm = st.text_input(
            t("confirm_delete_relationship"),
            key="delete_relationship_confirm",
        )
        if st.button(t("delete_relationship"), key="delete_relationship_btn"):
            if delete_confirm != "DELETE":
                st.error(t("confirmation_mismatch_required"))
                return

            selected_relationship = relationship_options[selected_relationship_label]
            try:
                delete_sql_foreign_key_relationship(
                    con,
                    selected_relationship["from_table"],
                    selected_relationship["from_column"],
                    selected_relationship["to_table"],
                    selected_relationship["to_column"],
                )
                st.success(t("relationship_deleted", relationship=selected_relationship_label))
                st.rerun()
            except Exception as exc:
                logging.exception("Failed to delete SQL foreign key relationship")
                st.error(str(exc))


def render_schema_visualization(con: duckdb.DuckDBPyConnection) -> None:
    tables = list_user_tables(con)
    relationships = get_relationships(con)

    st.header(t("schema_visualization"))

    if not tables:
        st.info(t("need_one_table_schema"))
        return

    diagram_html = build_schema_designer_html(con, tables, relationships)
    components.html(diagram_html, height=900, scrolling=True)

    if relationships.empty:
        st.info(t("no_relationships"))
    else:
        st.subheader(t("saved_relationships"))
        st.dataframe(
            relationships.drop(columns=["id"]),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader(t("tables"))
    selected_table = st.selectbox(t("inspect_table"), tables, key="schema_table")
    st.dataframe(get_table_schema(con, selected_table), use_container_width=True, hide_index=True)


def render_related_query(con: duckdb.DuckDBPyConnection) -> None:
    tables = list_user_tables(con)
    relationships = get_relationships(con)

    st.header(t("query_related_data"))

    if not tables:
        st.info(t("upload_to_start"))
        return

    template_to_apply = render_query_template_manager(tables)

    if relationships.empty:
        st.info(t("query_no_relationships"))
        return

    if template_to_apply:
        st.session_state.query_base_table = template_to_apply.get("base_table")

    base_table = st.selectbox(t("base_table"), tables, key="query_base_table")
    paths = get_reachable_tables(base_table, relationships)
    reachable_tables = sorted([table for table in paths.keys() if table != base_table])

    if not reachable_tables:
        st.info(t("query_no_relationships"))
        return

    related_tables_key = f"query_related_{base_table}"
    if template_to_apply and template_to_apply.get("base_table") == base_table:
        st.session_state[related_tables_key] = [
            table
            for table in template_to_apply.get("related_tables", [])
            if table in reachable_tables
        ]
    elif related_tables_key in st.session_state:
        st.session_state[related_tables_key] = [
            table
            for table in st.session_state[related_tables_key]
            if table in reachable_tables
        ]

    selected_related_tables = st.multiselect(
        t("related_tables"),
        reachable_tables,
        default=reachable_tables[:1],
        key=related_tables_key,
    )
    query_tables = [base_table] + selected_related_tables
    column_options = make_column_options(con, query_tables)
    option_labels = list(column_options.keys())
    default_columns = [
        label
        for label in option_labels
        if label.startswith(f"{base_table}.")
    ][:8]

    result_columns_key = f"query_columns_{base_table}_{'_'.join(selected_related_tables)}"
    if template_to_apply and template_to_apply.get("base_table") == base_table:
        applied_result_columns = labels_from_column_refs(
            template_to_apply.get("result_columns", []),
            option_labels,
        )
        st.session_state[result_columns_key] = applied_result_columns or default_columns
    elif result_columns_key in st.session_state:
        st.session_state[result_columns_key] = [
            label
            for label in st.session_state[result_columns_key]
            if label in option_labels
        ]

    selected_column_labels = st.multiselect(
        t("result_columns"),
        option_labels,
        default=default_columns,
        key=result_columns_key,
    )
    if not selected_column_labels:
        st.warning(t("select_at_least_one_column"))
        return

    search_left, search_right = st.columns([2, 3])
    if template_to_apply and template_to_apply.get("base_table") == base_table:
        st.session_state.query_search = template_to_apply.get("search_text", "")
    search = search_left.text_input(t("search_text"), key="query_search")
    search_columns_key = f"query_search_columns_{base_table}_{'_'.join(selected_related_tables)}"
    if template_to_apply and template_to_apply.get("base_table") == base_table:
        applied_search_columns = labels_from_column_refs(
            template_to_apply.get("search_columns", []),
            option_labels,
        )
        st.session_state[search_columns_key] = applied_search_columns or selected_column_labels
    elif search_columns_key in st.session_state:
        st.session_state[search_columns_key] = [
            label
            for label in st.session_state[search_columns_key]
            if label in option_labels
        ]
    search_column_labels = search_right.multiselect(
        t("search_columns"),
        option_labels,
        default=selected_column_labels,
        key=search_columns_key,
    )

    sort_left, sort_mid, sort_right = st.columns([2, 1, 1])
    sort_options = [""] + option_labels
    if template_to_apply and template_to_apply.get("base_table") == base_table:
        applied_sort_labels = labels_from_column_refs(
            [template_to_apply.get("sort_column")] if template_to_apply.get("sort_column") else [],
            option_labels,
        )
        st.session_state.query_sort_by = applied_sort_labels[0] if applied_sort_labels else ""
        st.session_state.query_sort_direction = (
            template_to_apply.get("sort_direction")
            if template_to_apply.get("sort_direction") in SORT_DIRECTIONS
            else "asc"
        )
        st.session_state.query_row_limit = normalize_row_limit(template_to_apply.get("row_limit"))
    elif st.session_state.get("query_sort_by") not in sort_options:
        st.session_state.query_sort_by = ""
    if st.session_state.get("query_sort_direction") not in SORT_DIRECTIONS:
        st.session_state.query_sort_direction = "asc"
    if "query_row_limit" in st.session_state:
        st.session_state.query_row_limit = normalize_row_limit(st.session_state.query_row_limit)

    sort_label = sort_left.selectbox(
        t("sort_by"),
        sort_options,
        key="query_sort_by",
        format_func=lambda option: t("no_sort") if option == "" else option,
    )
    sort_direction = sort_mid.selectbox(
        t("sort_direction"),
        SORT_DIRECTIONS,
        key="query_sort_direction",
        format_func=sort_direction_label,
    )
    row_limit = sort_right.number_input(
        t("row_limit"),
        min_value=1,
        max_value=10000,
        value=1000,
        step=100,
        key="query_row_limit",
    )

    selected_columns = [column_options[label] for label in selected_column_labels]
    search_columns = [column_options[label] for label in search_column_labels]
    sort_column = None if sort_label == "" else column_options[sort_label]

    try:
        query, params = build_related_query(
            selected_columns,
            base_table,
            selected_related_tables,
            paths,
            search,
            search_columns,
            sort_column,
            sort_direction,
            int(row_limit),
        )
        result = con.execute(query, params).fetchdf()
    except Exception as exc:
        logging.exception("Failed to run related table query")
        st.error(str(exc))
        return

    with st.expander(t("show_sql")):
        st.code(query, language="sql")

    st.dataframe(result, use_container_width=True, hide_index=True)
    render_export_buttons(result, f"{base_table}_related_query")

    save_left, save_right = st.columns([3, 1])
    template_name = save_left.text_input(t("query_template_name"), key="query_template_name")
    if save_right.button(t("save_query_template"), key="save_query_template"):
        if not template_name.strip():
            st.error(t("query_template_name_required"))
        else:
            query_template = make_query_template(
                template_name,
                base_table,
                selected_related_tables,
                selected_column_labels,
                search,
                search_column_labels,
                sort_label,
                sort_direction,
                int(row_limit),
                column_options,
                query,
            )
            upsert_query_template(query_template)
            st.success(t("query_template_saved", name=query_template["name"]))
            st.rerun()


def render_table_actions(con: duckdb.DuckDBPyConnection, selected_table: str) -> None:
    with st.expander(t("table_actions")):
        st.caption(t("table_actions_caption"))

        rename_left, rename_right = st.columns([2, 1])
        new_table_name = rename_left.text_input(
            t("new_table_name"),
            value=selected_table,
            key=f"rename_{selected_table}",
        )
        normalized_new_name = normalize_identifier(new_table_name, "table")

        if rename_right.button(t("rename_table"), key=f"rename_btn_{selected_table}"):
            try:
                if normalized_new_name == selected_table:
                    st.info(t("different_table_name"))
                elif normalized_new_name in list_user_tables(con):
                    st.error(t("table_exists", table=normalized_new_name))
                else:
                    con.execute(
                        f"ALTER TABLE {quote_identifier(selected_table)} RENAME TO {quote_identifier(normalized_new_name)}"
                    )
                    st.success(t("renamed_to", table=normalized_new_name))
                    st.rerun()
            except Exception as exc:
                logging.exception("Failed to rename table: %s", selected_table)
                st.error(str(exc))

        clear_confirm = st.text_input(
            t("confirm_clear", table=selected_table),
            key=f"clear_confirm_{selected_table}",
        )
        if st.button(t("clear_rows"), key=f"clear_btn_{selected_table}"):
            if clear_confirm != selected_table:
                st.error(t("confirmation_mismatch_table"))
            else:
                try:
                    con.execute(f"DELETE FROM {quote_identifier(selected_table)}")
                    st.success(t("rows_cleared", table=selected_table))
                    st.rerun()
                except Exception as exc:
                    logging.exception("Failed to clear table: %s", selected_table)
                    st.error(str(exc))

        delete_confirm = st.text_input(
            t("confirm_delete", table=selected_table),
            key=f"delete_confirm_{selected_table}",
        )
        if st.button(t("delete_table"), key=f"delete_btn_{selected_table}"):
            if delete_confirm != f"DELETE {selected_table}":
                st.error(t("confirmation_mismatch_required"))
            else:
                try:
                    con.execute(f"DROP TABLE {quote_identifier(selected_table)}")
                    st.success(t("deleted_table", table=selected_table))
                    st.rerun()
                except Exception as exc:
                    logging.exception("Failed to delete table: %s", selected_table)
                    st.error(str(exc))


def render_column_editor(con: duckdb.DuckDBPyConnection, selected_table: str) -> None:
    with st.expander(t("column_editor")):
        st.caption(t("column_editor_caption"))
        st.warning(t("type_change_warning"))

        schema = get_table_schema(con, selected_table)
        current_primary_keys = get_primary_key_columns(con, selected_table)
        editable_schema = [
            {
                "position": index + 1,
                "current_name": str(row["column_name"]),
                "new_name": str(row["column_name"]),
                "current_type": str(row["column_type"]),
                "new_type": str(row["column_type"])
                if str(row["column_type"]) in SUPPORTED_TYPES
                else "VARCHAR",
                "current_primary_key": str(row["column_name"]) in current_primary_keys,
                "new_primary_key": str(row["column_name"]) in current_primary_keys,
            }
            for index, (_, row) in enumerate(schema.iterrows())
        ]

        edited_columns = st.data_editor(
            editable_schema,
            use_container_width=True,
            hide_index=True,
            disabled=["current_name", "current_type", "current_primary_key"],
            column_config={
                "position": st.column_config.NumberColumn(t("position"), min_value=1, step=1, required=True),
                "current_name": st.column_config.TextColumn(t("current_name")),
                "new_name": st.column_config.TextColumn(t("new_name"), required=True),
                "current_type": st.column_config.TextColumn(t("current_type")),
                "new_type": st.column_config.SelectboxColumn(t("new_type"), options=SUPPORTED_TYPES, required=True),
                "current_primary_key": st.column_config.CheckboxColumn(t("primary_key")),
                "new_primary_key": st.column_config.CheckboxColumn(t("primary_key"), help=t("primary_key_warning")),
            },
            key=f"columns_editor_{selected_table}",
        )

        type_changes = [
            row for row in edited_columns
            if str(row["new_type"]) != str(row["current_type"])
        ]
        rename_changes = [
            row for row in edited_columns
            if normalize_identifier(str(row["new_name"])) != str(row["current_name"])
        ]
        new_primary_keys = [
            normalize_identifier(str(row["new_name"]))
            for row in edited_columns
            if row.get("new_primary_key")
        ]
        primary_key_changed = new_primary_keys != current_primary_keys
        current_order = [str(row["column_name"]) for _, row in schema.iterrows()]
        sorted_columns = sorted(
            edited_columns,
            key=lambda row: (int(row.get("position") or 999999), str(row["current_name"])),
        )
        new_column_order = [
            normalize_identifier(str(row["new_name"]))
            for row in sorted_columns
        ]
        column_order_changed = new_column_order != current_order

        if type_changes:
            changed = ", ".join(
                f'{row["current_name"]}: {row["current_type"]} -> {row["new_type"]}'
                for row in type_changes
            )
            st.warning(t("pending_type_changes", changes=changed))
        if column_order_changed:
            st.warning(t("reorder_warning"))

        confirm_text = st.text_input(
            t("confirm_apply_columns", table=selected_table),
            key=f"column_confirm_{selected_table}",
        )

        if st.button(t("apply_column_changes"), key=f"apply_columns_{selected_table}"):
            if not rename_changes and not type_changes and not primary_key_changed and not column_order_changed:
                st.info(t("no_column_changes"))
                return

            if type_changes and confirm_text != f"APPLY {selected_table}":
                st.error(t("confirm_type_changes"))
                return

            try:
                used_names: set[str] = set()
                for row in edited_columns:
                    normalized_name = normalize_identifier(str(row["new_name"]))
                    if normalized_name in used_names:
                        raise ValueError(f"Duplicate column name: {normalized_name}")
                    used_names.add(normalized_name)

                column_renames = {
                    str(row["current_name"]): normalize_identifier(str(row["new_name"]))
                    for row in edited_columns
                    if normalize_identifier(str(row["new_name"])) != str(row["current_name"])
                }
                updated_primary_keys = [
                    normalize_identifier(str(row["new_name"]))
                    for row in edited_columns
                    if row.get("new_primary_key")
                ]
                updated_foreign_keys = []
                for relationship in get_table_foreign_key_rows(con, selected_table):
                    relationship["from_column"] = column_renames.get(
                        relationship["from_column"],
                        relationship["from_column"],
                    )
                    updated_foreign_keys.append(relationship)

                rebuilt_columns = []
                rebuilt_definitions = []
                rebuilt_select_parts = []
                for row in sorted_columns:
                    current_name = str(row["current_name"])
                    new_name = normalize_identifier(str(row["new_name"]))
                    new_type = str(row["new_type"])
                    current_type = str(row["current_type"])
                    rebuilt_columns.append(new_name)
                    rebuilt_definitions.append(f"{quote_identifier(new_name)} {new_type}")
                    if new_type == current_type:
                        rebuilt_select_parts.append(
                            f"{quote_identifier(current_name)} AS {quote_identifier(new_name)}"
                        )
                    else:
                        rebuilt_select_parts.append(
                            f"TRY_CAST({quote_identifier(current_name)} AS {new_type}) AS {quote_identifier(new_name)}"
                        )

                rebuild_table_preserving_references(
                    con,
                    selected_table,
                    updated_primary_keys,
                    updated_foreign_keys,
                    column_definitions=rebuilt_definitions,
                    target_columns=rebuilt_columns,
                    select_parts=rebuilt_select_parts,
                    source_relation=quote_identifier(selected_table),
                    column_renames=column_renames,
                )

                st.success(t("column_changes_applied"))
                st.rerun()
            except Exception as exc:
                logging.exception("Failed to edit columns for table: %s", selected_table)
                st.error(str(exc))


def render_data_browser(con: duckdb.DuckDBPyConnection) -> None:
    tables = list_user_tables(con)
    st.header(t("browse_data"))

    if not tables:
        st.info(t("upload_to_start"))
        return

    selected_table = st.selectbox(t("select_table"), tables)
    render_table_actions(con, selected_table)
    render_column_editor(con, selected_table)

    search = st.text_input(t("search_text"))
    columns = get_columns(con, selected_table)

    query = f"SELECT * FROM {quote_identifier(selected_table)}"
    if search:
        conditions = [
            f"CAST({quote_identifier(column)} AS VARCHAR) ILIKE ?"
            for column in columns
        ]
        query += " WHERE " + " OR ".join(conditions)
        params = [f"%{search}%"] * len(columns)
    else:
        params = []

    query += " LIMIT 1000"
    result = con.execute(query, params).fetchdf()

    st.dataframe(result, use_container_width=True, hide_index=True)
    render_export_buttons(result, f"{selected_table}_export")


def main() -> None:
    st.set_page_config(page_title="Data Constructor", layout="wide")

    current_language = get_language()
    selected_language = st.sidebar.selectbox(
        t("language"),
        LANGUAGE_CODES,
        index=LANGUAGE_CODES.index(current_language) if current_language in LANGUAGE_CODES else 0,
        format_func=language_label,
    )
    st.session_state.language = selected_language

    selected_theme = st.sidebar.selectbox(
        t("theme"),
        THEME_OPTIONS,
        index=THEME_OPTIONS.index(get_theme()),
        format_func=theme_label,
    )
    st.session_state.theme = selected_theme
    apply_runtime_theme()

    st.title(t("app_title"))

    Path("data").mkdir(exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(DB_PATH)
    cleanup_rebuild_tables(con)

    tab_import, tab_relationships, tab_schema, tab_query, tab_browse = st.tabs(
        [t("import"), t("relationships"), t("schema"), t("query"), t("browse")]
    )
    with tab_import:
        render_upload_import(con)
    with tab_relationships:
        render_relationships(con)
    with tab_schema:
        render_schema_visualization(con)
    with tab_query:
        render_related_query(con)
    with tab_browse:
        render_data_browser(con)


if __name__ == "__main__":
    main()
