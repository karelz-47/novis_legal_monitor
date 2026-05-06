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

if "last_summary" not in st.session_state:
    st.session_state["last_summary"] = None
if "last_records" not in st.session_state:
    st.session_state["last_records"] = []


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


search_query = st.text_input(
    "What name or keyword should we look for?",
    value="",
    help=(
        "Type a company name, person name, or keyword. "
        "We look for this text without case sensitivity "
        "(for example, 'Acme' matches 'ACME')."
    ),
)
search_scope = st.radio(
    "Where should we look for that text?",
    options=[
        ("full_text", "Every available field"),
        ("targeted", "Only names (proposers and corporate body name)"),
        ("combined", "Names first, then all other fields"),
    ],
    format_func=lambda item: item[1],
    horizontal=False,
    help=(
        "This setting controls which data fields are checked in each API record. "
        "'Names first, then all other fields' starts with name fields and then checks the rest."
    ),
)
window_mode = st.radio(
    "How far back should we search?",
    options=["Last N days", "Custom date range"],
    horizontal=True,
    help=(
        "Choose a rolling period (for example, last 30 days) "
        "or set exact start and end dates in UTC."
    ),
)

if window_mode == "Last N days":
    trailing_days = st.number_input(
        "Number of days to include",
        min_value=0,
        value=30,
        step=1,
        help="Example: 30 means from today back to 30 days ago (UTC).",
    )
    date_from = None
    date_to = None
else:
    trailing_days = None
    default_from = (dt.datetime.utcnow() - dt.timedelta(days=30)).date()
    date_from = st.date_input(
        "Start date (UTC)",
        value=default_from,
        help="Beginning of the period to check.",
    )
    date_to = st.date_input(
        "End date (UTC)",
        value=dt.datetime.utcnow().date(),
        help="Final date to include in the search period.",
    )

current_dir = os.path.dirname(os.path.abspath(__file__))
ts_path = os.path.join(current_dir, "last_run.txt")

last_ts = monitor.load_last_run_timestamp(ts_path)
if last_ts:
    last_dt = dt.datetime.fromisoformat(last_ts.rstrip("Z"))
    st.write(f"Last update run: {last_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
else:
    st.write("No previous runs recorded.")

if st.button("Run update"):
    with st.spinner("Fetching updates..."):
        if window_mode == "Last N days":
            summary = monitor.perform_update_last_n_days(
                int(trailing_days),
                query=search_query,
                search_mode=search_scope[0],
                send_notifications=False,
            )
        else:
            since_dt = dt.datetime.combine(date_from, dt.time.min)
            to_dt = dt.datetime.combine(date_to, dt.time.max)
            since = since_dt.isoformat() + "Z"
            to_timestamp = to_dt.isoformat() + "Z"
            summary = monitor.perform_update(
                since,
                query=search_query,
                search_mode=search_scope[0],
                send_notifications=False,
                to_timestamp=to_timestamp,
            )

        monitor.save_last_run_timestamp(ts_path, summary["timestamp"])

    st.session_state["last_summary"] = summary
    st.session_state["last_records"] = summary.get("records", [])
    st.success("Update complete.")

if st.button("Clear results"):
    st.session_state["last_summary"] = None
    st.session_state["last_records"] = []
    st.success("Cleared previous search results.")

summary = st.session_state.get("last_summary")
records = st.session_state.get("last_records", [])
if summary is not None:
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

    st.subheader("Email Results")
    recipient_input = st.text_input(
        "Recipients (comma-separated emails)",
        value="",
        help="No email is sent automatically. Click the button below to send.",
    )
    recipients = [item.strip() for item in recipient_input.split(",") if item.strip()]
    if st.button("Send via email"):
        with st.spinner("Sending email..."):
            email_result = monitor.send_email(records, recipients=recipients)
        if email_result:
            st.success("Email sent.")
        elif not recipients:
            st.warning("Please add at least one recipient.")
        else:
            st.error("Email could not be sent. Check configuration and logs.")
