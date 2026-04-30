"""
Streamlit front‑end for the NOVIS monitor.

This simple Streamlit application allows the user to trigger an update
cycle manually and displays a summary of the most recent run.  It
loads the timestamp of the last run from the monitor's `last_run.txt`
file and shows when the last update occurred.  Upon pressing the
"Run update" button, it executes the monitor logic (fetching changes
from the Slovensko.Digital data hub, filtering for NOVIS records and
sending an email if necessary) and updates the timestamp file.

To launch the app, run the following from the project root:

    streamlit run novis_monitor/streamlit_app.py

"""

import streamlit as st
import datetime as dt
import os

import monitor

st.set_page_config(page_title="NOVIS Monitor", layout="wide")

st.title("NOVIS Liquidation & Bankruptcy Monitor")

search_query = st.text_input("Search text", value="NOVIS", help="Case-insensitive text search across all record fields.")

default_from = (dt.datetime.utcnow() - dt.timedelta(days=30)).date()
date_from = st.date_input("From date (UTC)", value=default_from)
date_to = st.date_input("To date (UTC)", value=dt.datetime.utcnow().date())

# Path to the timestamp file
current_dir = os.path.dirname(os.path.abspath(__file__))
ts_path = os.path.join(current_dir, "last_run.txt")

last_ts = monitor.load_last_run_timestamp(ts_path)
if last_ts:
    last_dt = dt.datetime.fromisoformat(last_ts.rstrip("Z"))
    st.write(f"Last update run: {last_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
else:
    st.write("No previous runs recorded.")

if st.button("Run update"):
    since_dt = dt.datetime.combine(date_from, dt.time.min)
    to_dt = dt.datetime.combine(date_to, dt.time.max)
    since = since_dt.isoformat() + "Z"
    to_timestamp = to_dt.isoformat() + "Z"
    with st.spinner("Fetching updates and sending notifications..."):
        summary = monitor.perform_update(since, query=search_query, to_timestamp=to_timestamp)
        # Save the timestamp
        monitor.save_last_run_timestamp(ts_path, summary["timestamp"])
    st.success("Update complete.")
    st.json(summary)
