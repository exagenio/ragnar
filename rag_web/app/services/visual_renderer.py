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
        "x_axis_column": "column_name",
        "y_axis_columns": ["column_name_1", "column_name_2", ...]
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

    # --- Extract axis info (support both old and new formats) ---
    x_axis = visual_spec.get("x_axis_column") or visual_spec.get("x_axis")

    # Handle y_axis_columns (new format) or y_axis (old format)
    y_axis_columns = visual_spec.get("y_axis_columns")
    if not y_axis_columns:
        # Backward compatibility: if old format exists, convert to list
        old_y = visual_spec.get("y_axis")
        y_axis_columns = [old_y] if old_y else []
    elif isinstance(y_axis_columns, str):
        # Normalize: if string provided, convert to list
        y_axis_columns = [y_axis_columns]

    chart_type = visual_spec.get("type")
    title = visual_spec.get("title", "")

    print("chart type = ", chart_type)
    print("x_axis = ", x_axis)
    print("y_axis_columns = ", y_axis_columns)

    fig = _build_figure(
        chart_type=chart_type,
        df=df,
        x=x_axis,
        y_columns=y_axis_columns,
        title=title,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig.update_layout(autosize=True)

    fig.write_image(
        str(output_path),
        width=1000,
        scale=2
    )

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
    y_columns: list[str] | None,
    title: str,
):
    """
    Build a Plotly figure based on chart type.
    Supports multiple y-axis columns for line and bar charts.
    """

    if not y_columns:
        y_columns = []

    if chart_type == "line_chart":
        _require_columns(df, [x] + y_columns)

        # If multiple y-columns, use Plotly's multi-line support
        if len(y_columns) == 1:
            fig = px.line(df, x=x, y=y_columns[0], title=title)
        else:
            # Multiple y-axes: pass list of columns
            fig = go.Figure()
            for y_col in y_columns:
                fig.add_trace(go.Scatter(
                    x=df[x],
                    y=df[y_col],
                    mode='lines+markers',
                    name=y_col
                ))
            fig.update_layout(title=title, xaxis_title=x)

    elif chart_type == "bar_chart":
        _require_columns(df, [x] + y_columns)

        # If multiple y-columns, create grouped bar chart
        if len(y_columns) == 1:
            fig = px.bar(df, x=x, y=y_columns[0], title=title)
        else:
            # Multiple y-axes: create grouped bars
            fig = go.Figure()
            for y_col in y_columns:
                fig.add_trace(go.Bar(
                    x=df[x],
                    y=df[y_col],
                    name=y_col
                ))
            fig.update_layout(
                title=title,
                xaxis_title=x,
                barmode='group'
            )

    elif chart_type == "pie_chart":
        # Pie charts only support ONE metric
        if len(y_columns) != 1:
            raise ValueError(f"Pie chart requires exactly one y-axis column, got {len(y_columns)}")
        _require_columns(df, [x, y_columns[0]])
        fig = px.pie(df, names=x, values=y_columns[0], title=title)

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

    elif chart_type == "combo_chart":
        _require_columns(df, [x] + y_columns)

        if len(y_columns) < 2:
            raise ValueError("Combo chart requires at least two y-axis columns")

        fig = go.Figure()

        # First metric → Bar
        fig.add_trace(
            go.Bar(
                x=df[x],
                y=df[y_columns[0]],
                name=y_columns[0],
                yaxis="y",
            )
        )

        # Remaining metrics → Line
        for y_col in y_columns[1:]:
            fig.add_trace(
                go.Scatter(
                    x=df[x],
                    y=df[y_col],
                    mode="lines+markers",
                    name=y_col,
                    yaxis="y",
                )
            )

        fig.update_layout(
            title=title,
            xaxis_title=x,
            yaxis_title="Value",
        )


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