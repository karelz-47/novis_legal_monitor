"""Streamlit front‑end for the legal monitor."""

from __future__ import annotations

import datetime as dt
import io
import os
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import monitor

st.set_page_config(page_title="Legal Monitor", layout="wide")

st.title("Liquidation & Bankruptcy Monitor")


def _flatten_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested JSON into table-friendly keys."""
    flattened: Dict[str, Any] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v)
        elif isinstance(value, list):
            flattened[prefix] = ", ".join(str(item) for item in value)
        else:
            flattened[prefix] = value

    walk("", record)
    return flattened


def _records_to_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame([_flatten_record(rec) for rec in records]).fillna("")


def _export_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Results")
    return output.getvalue()


def _export_word(df: pd.DataFrame) -> bytes:
    doc = Document()
    doc.add_heading("Legal Monitor Results", level=1)
    doc.add_paragraph(f"Generated: {dt.datetime.utcnow().isoformat()}Z")

    if df.empty:
        doc.add_paragraph("No results found.")
    else:
        table = doc.add_table(rows=1, cols=len(df.columns))
        hdr_cells = table.rows[0].cells
        for i, col in enumerate(df.columns):
            hdr_cells[i].text = str(col)

        for _, row in df.iterrows():
            cells = table.add_row().cells
            for i, col in enumerate(df.columns):
                cells[i].text = str(row[col])

    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def _export_pdf(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 40
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Legal Monitor Results")
    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Generated: {dt.datetime.utcnow().isoformat()}Z")
    y -= 20

    if df.empty:
        c.drawString(40, y, "No results found.")
    else:
        for idx, row in df.iterrows():
            c.setFont("Helvetica-Bold", 9)
            c.drawString(40, y, f"Record {idx + 1}")
            y -= 14
            c.setFont("Helvetica", 8)
            for col in df.columns:
                line = f"{col}: {row[col]}"
                if len(line) > 150:
                    line = line[:147] + "..."
                c.drawString(50, y, line)
                y -= 12
                if y < 40:
                    c.showPage()
                    y = height - 40
                    c.setFont("Helvetica", 8)
            y -= 6
            if y < 40:
                c.showPage()
                y = height - 40
                c.setFont("Helvetica", 8)

    c.save()
    return output.getvalue()


search_query = st.text_input("Search text", value="", help="Case-insensitive text search across all record fields.")
window_mode = st.radio("Time window", options=["Last N days", "Custom date range"], horizontal=True)

if window_mode == "Last N days":
    trailing_days = st.number_input("Days back", min_value=0, value=30, step=1)
    date_from = None
    date_to = None
else:
    trailing_days = None
    default_from = (dt.datetime.utcnow() - dt.timedelta(days=30)).date()
    date_from = st.date_input("From date (UTC)", value=default_from)
    date_to = st.date_input("To date (UTC)", value=dt.datetime.utcnow().date())

current_dir = os.path.dirname(os.path.abspath(__file__))
ts_path = os.path.join(current_dir, "last_run.txt")

last_ts = monitor.load_last_run_timestamp(ts_path)
if last_ts:
    last_dt = dt.datetime.fromisoformat(last_ts.rstrip("Z"))
    st.write(f"Last update run: {last_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
else:
    st.write("No previous runs recorded.")

if st.button("Run update"):
    with st.spinner("Fetching updates and sending notifications..."):
        if window_mode == "Last N days":
            summary = monitor.perform_update_last_n_days(int(trailing_days), query=search_query)
        else:
            since_dt = dt.datetime.combine(date_from, dt.time.min)
            to_dt = dt.datetime.combine(date_to, dt.time.max)
            since = since_dt.isoformat() + "Z"
            to_timestamp = to_dt.isoformat() + "Z"
            summary = monitor.perform_update(since, query=search_query, to_timestamp=to_timestamp)

        monitor.save_last_run_timestamp(ts_path, summary["timestamp"])

    st.success("Update complete.")
    records = summary.get("records", [])
    df = _records_to_dataframe(records)

    st.subheader("Run Summary")
    st.write({k: v for k, v in summary.items() if k != "records"})

    st.subheader("Matching Results")
    if df.empty:
        st.info("No matching results found for the selected filters.")
    else:
        st.dataframe(df, use_container_width=True)

    st.subheader("Download Results")
    st.download_button(
        "Download XLSX",
        data=_export_excel(df),
        file_name="results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Download Word",
        data=_export_word(df),
        file_name="results.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    st.download_button(
        "Download PDF",
        data=_export_pdf(df),
        file_name="results.pdf",
        mime="application/pdf",
    )
