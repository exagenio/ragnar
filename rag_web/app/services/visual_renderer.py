from typing import Dict, Any
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ==========================
# PUBLIC ENTRY POINT
# ==========================

def render_visual(
    *,
    visual_spec: Dict[str, Any],
    sql_result: Dict[str, Any],
    output_path: Path,
) -> Dict[str, Any]:
    """
    Render a visual (chart/table) from SQL result data and save as PNG.

    visual_spec example:
    {
        "type": "line_chart" | "bar_chart" | "pie_chart" | "table",
        "title": "string",
        "x_axis": "column_name",
        "y_axis": "column_name"
    }

    sql_result example:
    {
        "columns": [...],
        "rows": [...]
    }
    """

    if not sql_result or "columns" not in sql_result or "rows" not in sql_result:
        raise ValueError("Invalid SQL result for visualization")

    df = pd.DataFrame(sql_result["rows"], columns=sql_result["columns"])

    # --- Normalize column aliases to visual_spec ---
    rename_map = {}

    if visual_spec.get("x_axis"):
        for col in df.columns:
            if col.lower().replace("_", " ") == visual_spec["x_axis"].lower():
                rename_map[col] = visual_spec["x_axis"]

    if visual_spec.get("y_axis"):
        for col in df.columns:
            if col.lower().replace("_", " ") == visual_spec["y_axis"].lower():
                rename_map[col] = visual_spec["y_axis"]

    df = df.rename(columns=rename_map)



    chart_type = visual_spec.get("type")
    title = visual_spec.get("title", "")
    x = visual_spec.get("x_axis")
    y = visual_spec.get("y_axis")
    print("chart type = ",chart_type,"\n\n\n\n\n")
    fig = _build_figure(
        chart_type=chart_type,
        df=df,
        x=x,
        y=y,
        title=title,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig.write_image(str(output_path), width=1000, height=500, scale=2)

    return {
        "status": "ok",
        "image_path": str(output_path),
        "chart_type": chart_type,
    }


# ==========================
# INTERNALS
# ==========================

def _build_figure(
    *,
    chart_type: str,
    df: pd.DataFrame,
    x: str | None,
    y: str | None,
    title: str,
):
    """
    Build a Plotly figure based on chart type.
    """

    if chart_type == "line_chart":
        _require_columns(df, [x, y])
        fig = px.line(df, x=x, y=y, title=title)

    elif chart_type == "bar_chart":
        _require_columns(df, [x, y])
        fig = px.bar(df, x=x, y=y, title=title)

    elif chart_type == "pie_chart":
        _require_columns(df, [x, y])
        fig = px.pie(df, names=x, values=y, title=title)

    elif chart_type == "table":
        fig = go.Figure(
            data=[
                go.Table(
                    header=dict(values=list(df.columns)),
                    cells=dict(values=[df[col] for col in df.columns]),
                )
            ]
        )
        fig.update_layout(title=title)

    else:
        raise ValueError(f"Unsupported visual type: {chart_type}")

    fig.update_layout(
        template="plotly_white",
        margin=dict(l=40, r=40, t=60, b=40),
    )

    return fig


def _require_columns(df: pd.DataFrame, columns: list):
    print("columns", df.columns)
    columns = [c for c in columns if c]  # ignore None
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for visualization: {missing}")