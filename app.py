import logging
import re
from html import escape
from pathlib import Path

import duckdb
import pandas as pd
import polars as pl
import streamlit as st
import streamlit.components.v1 as components


DB_PATH = "data/app.duckdb"
RAW_DIR = Path("data/raw")
LOG_PATH = Path("data/app.log")
CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1251", "windows-1251"]
SUPPORTED_TYPES = ["VARCHAR", "INTEGER", "BIGINT", "DOUBLE", "BOOLEAN", "DATE", "TIMESTAMP"]
LANGUAGE_OPTIONS = {"English": "en", "Українська": "uk"}
THEME_OPTIONS = ["light", "dark"]
TRANSLATIONS = {
    "en": {
        "language": "Language",
        "theme": "Theme",
        "light_theme": "Light",
        "dark_theme": "Dark",
        "app_title": "Data Constructor",
        "import": "Import",
        "relationships": "Relationships",
        "schema": "Schema",
        "browse": "Browse",
        "create_table_from_file": "Create table from file",
        "upload_file": "Upload CSV or Excel",
        "details_written": "Details were written to {path}",
        "preview": "Preview",
        "table_name": "Table name",
        "column_proposal": "Column proposal",
        "include": "Include",
        "source_column": "Source column",
        "source_column_help": "Leave empty for a new blank column.",
        "column_name": "Column name",
        "data_type": "Data type",
        "create_or_replace_table": "Create or replace table",
        "table_created": "Table created: {table}",
        "need_two_tables": "Create at least two tables to define relationships.",
        "from_table": "From table",
        "to_table": "To table",
        "from_column": "From column",
        "relationship": "Relationship",
        "to_column": "To column",
        "save_relationship": "Save relationship",
        "relationship_saved": "Relationship saved.",
        "schema_visualization": "Schema visualization",
        "need_one_table_schema": "Create at least one table to visualize the schema.",
        "no_relationships": "No relationships saved yet.",
        "saved_relationships": "Saved relationships",
        "tables": "Tables",
        "inspect_table": "Inspect table",
        "table_actions": "Table actions",
        "table_actions_caption": "Rename, clear rows, or delete the selected table.",
        "new_table_name": "New table name",
        "rename_table": "Rename table",
        "different_table_name": "Enter a different table name.",
        "table_exists": "Table already exists: {table}",
        "renamed_to": "Renamed to: {table}",
        "confirm_clear": "Type {table} to confirm clearing rows",
        "clear_rows": "Clear table rows",
        "confirmation_mismatch_table": "Confirmation does not match the selected table name.",
        "rows_cleared": "Rows cleared: {table}",
        "confirm_delete": "Type DELETE {table} to confirm table deletion",
        "delete_table": "Delete table",
        "confirmation_mismatch_required": "Confirmation does not match the required text.",
        "deleted_table": "Deleted table: {table}",
        "column_editor": "Column editor",
        "column_editor_caption": "Rename columns or change data types for the selected table.",
        "type_change_warning": "Changing a column type can fail or change stored values if existing data cannot be safely converted.",
        "current_name": "Current name",
        "new_name": "New name",
        "current_type": "Current type",
        "new_type": "New type",
        "pending_type_changes": "Pending type changes: {changes}",
        "confirm_apply_columns": "Type APPLY {table} to apply column changes",
        "apply_column_changes": "Apply column changes",
        "no_column_changes": "No column changes to apply.",
        "confirm_type_changes": "Confirm type changes before applying.",
        "column_changes_applied": "Column changes applied.",
        "browse_data": "Browse data",
        "upload_to_start": "Upload a CSV or Excel file to start.",
        "select_table": "Select table",
        "search_text": "Search text",
        "export_csv": "Export visible result to CSV",
        "unsupported_file_type": "Unsupported file type. Upload CSV, XLSX, or XLSM.",
    },
    "uk": {
        "language": "Мова",
        "theme": "Тема",
        "light_theme": "Світла",
        "dark_theme": "Темна",
        "app_title": "Data Constructor",
        "import": "Імпорт",
        "relationships": "Зв'язки",
        "schema": "Схема",
        "browse": "Дані",
        "create_table_from_file": "Створити таблицю з файлу",
        "upload_file": "Завантажити CSV або Excel",
        "details_written": "Деталі записані в {path}",
        "preview": "Попередній перегляд",
        "table_name": "Назва таблиці",
        "column_proposal": "Пропозиція колонок",
        "include": "Включити",
        "source_column": "Колонка джерела",
        "source_column_help": "Залиш порожнім для нової пустої колонки.",
        "column_name": "Назва колонки",
        "data_type": "Тип даних",
        "create_or_replace_table": "Створити або замінити таблицю",
        "table_created": "Таблицю створено: {table}",
        "need_two_tables": "Створи щонайменше дві таблиці, щоб додати зв'язки.",
        "from_table": "З таблиці",
        "to_table": "До таблиці",
        "from_column": "З колонки",
        "relationship": "Зв'язок",
        "to_column": "До колонки",
        "save_relationship": "Зберегти зв'язок",
        "relationship_saved": "Зв'язок збережено.",
        "schema_visualization": "Візуалізація схеми",
        "need_one_table_schema": "Створи щонайменше одну таблицю, щоб побачити схему.",
        "no_relationships": "Збережених зв'язків ще немає.",
        "saved_relationships": "Збережені зв'язки",
        "tables": "Таблиці",
        "inspect_table": "Переглянути таблицю",
        "table_actions": "Дії з таблицею",
        "table_actions_caption": "Перейменування, очистка або видалення вибраної таблиці.",
        "new_table_name": "Нова назва таблиці",
        "rename_table": "Перейменувати таблицю",
        "different_table_name": "Введи іншу назву таблиці.",
        "table_exists": "Таблиця вже існує: {table}",
        "renamed_to": "Перейменовано на: {table}",
        "confirm_clear": "Введи {table}, щоб підтвердити очистку рядків",
        "clear_rows": "Очистити рядки таблиці",
        "confirmation_mismatch_table": "Підтвердження не збігається з назвою вибраної таблиці.",
        "rows_cleared": "Рядки очищено: {table}",
        "confirm_delete": "Введи DELETE {table}, щоб підтвердити видалення таблиці",
        "delete_table": "Видалити таблицю",
        "confirmation_mismatch_required": "Підтвердження не збігається з потрібним текстом.",
        "deleted_table": "Таблицю видалено: {table}",
        "column_editor": "Редактор колонок",
        "column_editor_caption": "Перейменування колонок або зміна типів даних вибраної таблиці.",
        "type_change_warning": "Зміна типу колонки може завершитись помилкою або змінити збережені значення, якщо дані не можна безпечно конвертувати.",
        "current_name": "Поточна назва",
        "new_name": "Нова назва",
        "current_type": "Поточний тип",
        "new_type": "Новий тип",
        "pending_type_changes": "Очікувані зміни типів: {changes}",
        "confirm_apply_columns": "Введи APPLY {table}, щоб застосувати зміни колонок",
        "apply_column_changes": "Застосувати зміни колонок",
        "no_column_changes": "Немає змін колонок для застосування.",
        "confirm_type_changes": "Підтвердь зміни типів перед застосуванням.",
        "column_changes_applied": "Зміни колонок застосовано.",
        "browse_data": "Перегляд даних",
        "upload_to_start": "Завантаж CSV або Excel файл, щоб почати.",
        "select_table": "Вибрати таблицю",
        "search_text": "Пошук",
        "export_csv": "Експорт видимого результату в CSV",
        "unsupported_file_type": "Непідтримуваний тип файлу. Завантаж CSV, XLSX або XLSM.",
    },
}

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
        proposal.append(
            {
                "include": True,
                "source_column": column,
                "column_name": suggested_name,
                "data_type": suggest_duckdb_type(dtype),
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


def ensure_meta_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS app_relationships (
            id BIGINT PRIMARY KEY,
            from_table VARCHAR NOT NULL,
            from_column VARCHAR NOT NULL,
            to_table VARCHAR NOT NULL,
            to_column VARCHAR NOT NULL,
            relationship_type VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
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
        SELECT id, from_table, from_column, relationship_type, to_table, to_column, created_at
        FROM app_relationships
        ORDER BY created_at DESC
        """
    ).fetchdf()


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
    card_width = 300
    card_gap_x = 110
    card_gap_y = 92
    columns_per_row = 3
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
        height = 58 + max(len(schema), 1) * 34

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
        height = 58 + max(len(schema), 1) * 34

        table_positions[table] = (x, y)
        table_heights[table] = height
        table_grid[table] = (row, col)

        rows = []
        for column_index, (_, column_row) in enumerate(schema.iterrows()):
            column_name = str(column_row["column_name"])
            column_type = str(column_row["column_type"])
            column_title = f"{column_name}: {column_type}"
            is_related = (table, column_name) in related_columns
            column_y = y + 58 + column_index * 34 + 17
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
            label_x = loop_x + 18
            label_y = min(start_y, end_y) + abs(end_y - start_y) / 2
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
                label_x = min(start_x, end_x) + abs(end_x - start_x) / 2
                label_y = bus_y - 4
                path = (
                    f"M {start_x} {start_y} "
                    f"L {start_lane_x} {start_y} "
                    f"L {start_lane_x} {bus_y} "
                    f"L {end_lane_x} {bus_y} "
                    f"L {end_lane_x} {end_y} "
                    f"L {end_x} {end_y}"
                )
            else:
                label_x = lane_x
                label_y = min(start_y, end_y) + abs(end_y - start_y) / 2 - 8
                path = f"M {start_x} {start_y} L {lane_x} {start_y} L {lane_x} {end_y} L {end_x} {end_y}"
        elif from_col == to_col:
            lane = next_route_lane(("same-col", from_col, min(from_row, to_row), max(from_row, to_row)))
            start_x, start_y = from_anchor["right"]
            end_x, end_y = to_anchor["right"]
            lane_x = start_x + 34 + lane * side_lane_step
            label_x = lane_x + 18
            label_y = min(start_y, end_y) + abs(end_y - start_y) / 2
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
            label_x = start_lane_x + (end_lane_x - start_lane_x) / 2
            label_y = bus_y - 4
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
            label_x = start_lane_x + (end_lane_x - start_lane_x) / 2
            label_y = bus_y - 4
            path = (
                f"M {start_x} {start_y} "
                f"L {start_lane_x} {start_y} "
                f"L {start_lane_x} {bus_y} "
                f"L {end_lane_x} {bus_y} "
                f"L {end_lane_x} {end_y} "
                f"L {end_x} {end_y}"
            )

        label = escape(
            f'{relationship["from_column"]} -> {relationship["to_column"]} ({relationship["relationship_type"]})'
        )

        lines.append(
            f"""
            <path d="{path}" />
            <circle cx="{start_x}" cy="{start_y}" r="4"></circle>
            <circle cx="{end_x}" cy="{end_y}" r="4"></circle>
            <text x="{label_x}" y="{label_y}" text-anchor="middle">{label}</text>
            """
        )

    return f"""
    <style>
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
            border: 1px solid var(--erd-border);
            background:
                linear-gradient(var(--erd-grid) 23px, transparent 24px),
                linear-gradient(90deg, var(--erd-grid) 23px, transparent 24px),
                var(--erd-canvas-bg);
            background-size: 24px 24px;
            border-radius: 6px;
            font-family: Arial, sans-serif;
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
        .erd-lines text {{
            fill: var(--erd-line);
            font-size: 11px;
            paint-order: stroke;
            stroke: var(--erd-label-stroke);
            stroke-width: 4px;
            stroke-linejoin: round;
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
            font-weight: 700;
            font-size: 13px;
            padding: 10px 12px;
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
            min-height: 34px;
            padding: 7px 10px;
            border-bottom: 1px solid var(--erd-row-border);
            font-size: 12px;
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
    """


def create_table_from_schema(
    con: duckdb.DuckDBPyConnection,
    df: pl.DataFrame,
    table_name: str,
    schema_rows: list[dict],
) -> None:
    selected_rows = [row for row in schema_rows if row.get("include")]
    if not selected_rows:
        raise ValueError("Select at least one column.")

    used: set[str] = set()
    select_parts = []
    for row in selected_rows:
        column_name = normalize_identifier(str(row["column_name"]))
        if column_name in used:
            raise ValueError(f"Duplicate column name: {column_name}")
        used.add(column_name)

        data_type = row["data_type"]
        if data_type not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported data type: {data_type}")

        source_column = row.get("source_column")
        if source_column:
            source_sql = quote_identifier(source_column)
        else:
            source_sql = "NULL"

        select_parts.append(
            f"TRY_CAST({source_sql} AS {data_type}) AS {quote_identifier(column_name)}"
        )

    con.register("uploaded_df", df)
    try:
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {quote_identifier(table_name)} AS
            SELECT {", ".join(select_parts)}
            FROM uploaded_df
            """
        )
    finally:
        con.unregister("uploaded_df")


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
    st.dataframe(df.head(25).to_pandas(), use_container_width=True)

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

    left, right = st.columns(2)
    from_table = left.selectbox(t("from_table"), tables, key="from_table")
    to_table = right.selectbox(t("to_table"), tables, key="to_table")

    from_columns = get_columns(con, from_table)
    to_columns = get_columns(con, to_table)

    rel_left, rel_mid, rel_right = st.columns(3)
    from_column = rel_left.selectbox(t("from_column"), from_columns)
    relationship_type = rel_mid.selectbox(t("relationship"), ["many-to-one", "one-to-one", "one-to-many", "many-to-many"])
    to_column = rel_right.selectbox(t("to_column"), to_columns)

    if st.button(t("save_relationship")):
        next_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM app_relationships").fetchone()[0]
        con.execute(
            """
            INSERT INTO app_relationships
                (id, from_table, from_column, to_table, to_column, relationship_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [next_id, from_table, from_column, to_table, to_column, relationship_type],
        )
        st.success(t("relationship_saved"))

    relationships = get_relationships(con).drop(columns=["id"])

    if not relationships.empty:
        st.dataframe(relationships, use_container_width=True, hide_index=True)


def render_schema_visualization(con: duckdb.DuckDBPyConnection) -> None:
    tables = list_user_tables(con)
    relationships = get_relationships(con)

    st.header(t("schema_visualization"))

    if not tables:
        st.info(t("need_one_table_schema"))
        return

    diagram_html = build_schema_designer_html(con, tables, relationships)
    components.html(diagram_html, height=680, scrolling=True)

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
                    con.execute(
                        "UPDATE app_relationships SET from_table = ? WHERE from_table = ?",
                        [normalized_new_name, selected_table],
                    )
                    con.execute(
                        "UPDATE app_relationships SET to_table = ? WHERE to_table = ?",
                        [normalized_new_name, selected_table],
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
                    con.execute(
                        "DELETE FROM app_relationships WHERE from_table = ? OR to_table = ?",
                        [selected_table, selected_table],
                    )
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
        editable_schema = [
            {
                "current_name": str(row["column_name"]),
                "new_name": str(row["column_name"]),
                "current_type": str(row["column_type"]),
                "new_type": str(row["column_type"])
                if str(row["column_type"]) in SUPPORTED_TYPES
                else "VARCHAR",
            }
            for _, row in schema.iterrows()
        ]

        edited_columns = st.data_editor(
            editable_schema,
            use_container_width=True,
            hide_index=True,
            disabled=["current_name", "current_type"],
            column_config={
                "current_name": st.column_config.TextColumn(t("current_name")),
                "new_name": st.column_config.TextColumn(t("new_name"), required=True),
                "current_type": st.column_config.TextColumn(t("current_type")),
                "new_type": st.column_config.SelectboxColumn(t("new_type"), options=SUPPORTED_TYPES, required=True),
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

        if type_changes:
            changed = ", ".join(
                f'{row["current_name"]}: {row["current_type"]} -> {row["new_type"]}'
                for row in type_changes
            )
            st.warning(t("pending_type_changes", changes=changed))

        confirm_text = st.text_input(
            t("confirm_apply_columns", table=selected_table),
            key=f"column_confirm_{selected_table}",
        )

        if st.button(t("apply_column_changes"), key=f"apply_columns_{selected_table}"):
            if not rename_changes and not type_changes:
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

                applied_renames = {}
                for row in edited_columns:
                    current_name = str(row["current_name"])
                    new_name = normalize_identifier(str(row["new_name"]))
                    if new_name == current_name:
                        continue

                    con.execute(
                        f"""
                        ALTER TABLE {quote_identifier(selected_table)}
                        RENAME COLUMN {quote_identifier(current_name)} TO {quote_identifier(new_name)}
                        """
                    )
                    applied_renames[current_name] = new_name

                for old_name, new_name in applied_renames.items():
                    con.execute(
                        "UPDATE app_relationships SET from_column = ? WHERE from_table = ? AND from_column = ?",
                        [new_name, selected_table, old_name],
                    )
                    con.execute(
                        "UPDATE app_relationships SET to_column = ? WHERE to_table = ? AND to_column = ?",
                        [new_name, selected_table, old_name],
                    )

                for row in edited_columns:
                    original_name = str(row["current_name"])
                    column_name = applied_renames.get(original_name, original_name)
                    new_type = str(row["new_type"])
                    current_type = str(row["current_type"])

                    if new_type == current_type:
                        continue

                    con.execute(
                        f"""
                        ALTER TABLE {quote_identifier(selected_table)}
                        ALTER COLUMN {quote_identifier(column_name)}
                        SET DATA TYPE {new_type}
                        USING TRY_CAST({quote_identifier(column_name)} AS {new_type})
                        """
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

    st.dataframe(result, use_container_width=True)

    csv = result.to_csv(index=False).encode("utf-8")
    st.download_button(
        t("export_csv"),
        csv,
        f"{selected_table}_export.csv",
        "text/csv",
    )


def main() -> None:
    st.set_page_config(page_title="Data Constructor", layout="wide")

    language_label = st.sidebar.selectbox(
        t("language"),
        list(LANGUAGE_OPTIONS.keys()),
        index=0 if get_language() == "en" else 1,
    )
    st.session_state.language = LANGUAGE_OPTIONS[language_label]

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
    ensure_meta_tables(con)

    tab_import, tab_relationships, tab_schema, tab_browse = st.tabs(
        [t("import"), t("relationships"), t("schema"), t("browse")]
    )
    with tab_import:
        render_upload_import(con)
    with tab_relationships:
        render_relationships(con)
    with tab_schema:
        render_schema_visualization(con)
    with tab_browse:
        render_data_browser(con)


if __name__ == "__main__":
    main()
