"""
Monitor module for tracking Slovak Commercial Journal (Obchodný vestník)
submissions for bankruptcy (konkurz), restructuring (restrukturalizácia)
and liquidation (likvidácia) involving companies whose names contain
"NOVIS".  

This module encapsulates the logic for querying the public
Slovensko.Digital data hub, filtering the returned records and sending
notification emails via the Resend email API.  It is designed to be
imported into a Streamlit front‑end but can also be executed as a
stand‑alone script.  When run directly, it performs a single update
cycle using the last timestamp stored in the `last_run.txt` file
located alongside the module.

The `fetch_changes` function handles pagination through the
synchronisation API.  The `filter_records_for_novis` function checks
whether any company names in the record contain the substring "NOVIS"
(case‑insensitive).  The `send_email` function uses the `resend`
Python SDK to deliver a structured HTML email to the desired
recipient.

Environment variables:
    RESEND_API_KEY      – API key for the Resend service.
    RESEND_FROM_EMAIL   – Email address verified with Resend that will
                           appear in the "From" field.
    RESEND_TO_EMAIL     – Destination email address; defaults to
                           "kzvolsky@novis.eu" when unset.

Usage from the command line:
    python monitor.py

This will check for new records since the last run and send a
notification if any matching records are found.  The timestamp of
successful runs is saved to `last_run.txt` for incremental updates.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import requests
import logging
from typing import Any, Dict, List, Optional

try:
    import resend  # type: ignore
    _RESEND_AVAILABLE = True
except ImportError:
    _RESEND_AVAILABLE = False

# Base URL for the Slovensko.Digital data hub
BASE_URL = "https://datahub.ekosystem.slovensko.digital/api/data"

# Endpoints for the issues we monitor.  Each entry consists of a human
# friendly name and the relative API path.  The `/sync` suffix is
# appended by the fetch_changes function.
DATASETS = [
    ("konkurz_restrukturalizacia_issues", "ov/konkurz_restrukturalizacia_issues"),
    ("konkurz_vyrovnanie_issues", "ov/konkurz_vyrovnanie_issues"),
    ("likvidator_issues", "ov/likvidator_issues"),
]

# Regular expression for case‑insensitive matching of "NOVIS"
NOVIS_PATTERN = re.compile(r"novis", re.IGNORECASE)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse_next_link(link_header: Optional[str]) -> Optional[str]:
    """Parse the HTTP Link header and extract the URL for the next page.

    The data hub's synchronisation API returns a `Link` response header
    when additional pages of results are available.  This helper
    extracts the URL associated with `rel="next"` from that header.

    Parameters
    ----------
    link_header: Optional[str]
        The raw value of the `Link` HTTP header.  May be None.

    Returns
    -------
    Optional[str]
        The URL to follow for the next batch of records, or None if
        there is no next link.
    """
    if not link_header:
        return None
    # The header can contain multiple comma‑separated links.  Each link
    # entry has the form: <url>; rel="next"
    parts = [part.strip() for part in link_header.split(",")]
    for part in parts:
        if "rel='next'" in part or 'rel="next"' in part:
            # Extract the URL between angle brackets
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None


def fetch_changes(dataset_path: str, since: str) -> List[Dict[str, Any]]:
    """Retrieve new or updated records for a given dataset since a timestamp.

    This function repeatedly requests pages from the synchronisation API
    until no `Link` header with `rel="next"` is provided.  Each page
    returns a list of JSON objects.  All records are appended to a
    single list which is returned.

    Parameters
    ----------
    dataset_path: str
        Relative path to the dataset, e.g. "ov/konkurz_restrukturalizacia_issues".
    since: str
        ISO 8601 timestamp.  Only records updated after this time are
        returned.

    Returns
    -------
    List[Dict[str, Any]]
        List containing all retrieved records.
    """
    records: List[Dict[str, Any]] = []
    url = f"{BASE_URL}/{dataset_path}/sync?since={since}"
    session = requests.Session()
    headers = {
        "Accept": "application/json",
        "User-Agent": "NOVIS monitor (https://github.com/novis_monitor)"
    }
    while url:
        resp = session.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.error("Failed to fetch %s: %s", url, resp.status_code)
            break
        try:
            data = resp.json()
        except ValueError as exc:
            logger.error("Error parsing JSON from %s: %s", url, exc)
            break
        if isinstance(data, list):
            records.extend(data)
        else:
            logger.warning("Unexpected response structure: %s", type(data))
        # Parse Link header for next URL
        next_url = parse_next_link(resp.headers.get("Link"))
        url = next_url
    return records


def record_contains_query(record: Dict[str, Any], query: str = "NOVIS") -> bool:
    """Check whether a record contains a query string anywhere.

    The Slovensko.Digital issue records differ in structure across
    datasets.  We inspect several potential fields:

    * For `konkurz_restrukturalizacia_issues`: the debtor's
      `corporate_body_name` and any proposers' `corporate_body_name`.
    * For `konkurz_vyrovnanie_issues` and `likvidator_issues`:
      the top‑level `corporate_body_name` field.

    Parameters
    ----------
    record: Dict[str, Any]
        The JSON object returned by the API.

    Returns
    -------
    bool
        True if any relevant name contains "NOVIS" (case‑insensitive),
        otherwise False.
    """
    if not query:
        return False
    payload = json.dumps(record, ensure_ascii=False, default=str)
    return query.lower() in payload.lower()


def filter_records_by_query(records: List[Dict[str, Any]], query: str = "NOVIS") -> List[Dict[str, Any]]:
    """Return only those records that contain the query text anywhere."""
    return [rec for rec in records if record_contains_query(rec, query=query)]


def _parse_record_datetime(record: Dict[str, Any]) -> Optional[_dt.datetime]:
    for key in ("updated_at", "released_date", "created_at"):
        value = record.get(key)
        if not value:
            continue
        try:
            parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def filter_records_by_date_range(
    records: List[Dict[str, Any]],
    from_dt: Optional[_dt.datetime],
    to_dt: Optional[_dt.datetime],
) -> List[Dict[str, Any]]:
    """Filter records to a datetime window using known date fields."""
    if from_dt is None and to_dt is None:
        return records
    result: List[Dict[str, Any]] = []
    for rec in records:
        rec_dt = _parse_record_datetime(rec)
        if rec_dt is None:
            continue
        if from_dt and rec_dt < from_dt:
            continue
        if to_dt and rec_dt > to_dt:
            continue
        result.append(rec)
    return result


def format_records_html(records: List[Dict[str, Any]]) -> str:
    """Construct an HTML representation of the records for inclusion in an email.

    Each record's key fields are rendered as a table for human
    readability.  Additional fields are included if present.

    Parameters
    ----------
    records: List[Dict[str, Any]]
        List of records to format.

    Returns
    -------
    str
        HTML string containing a summary of the records.
    """
    if not records:
        return "<p>No relevant records found.</p>"
    html_parts = ["<h2>New NOVIS records</h2>"]
    for idx, rec in enumerate(records, 1):
        html_parts.append(f"<h3>Record {idx}</h3>")
        rows = []
        # Choose fields to display
        fields = {
            "ID": rec.get("id"),
            "Court": rec.get("court_name"),
            "File reference": rec.get("file_reference"),
            "Released date": rec.get("released_date"),
            "Type": rec.get("kind"),
            "Debtor company": None,
            "Company CIN": None,
        }
        # Populate debtor
        debtor = rec.get("debtor")
        if debtor and isinstance(debtor, dict):
            fields["Debtor company"] = debtor.get("corporate_body_name")
            fields["Company CIN"] = debtor.get("cin")
        else:
            # fallback to top level
            fields["Debtor company"] = rec.get("corporate_body_name")
            fields["Company CIN"] = rec.get("cin")
        for key, value in fields.items():
            if value is not None:
                rows.append(f"<tr><th style='text-align:left;padding:4px'>{key}</th><td style='padding:4px'>{value}</td></tr>")
        # Additional text fields
        for text_field in ["heading", "decision", "announcement", "advice"]:
            value = rec.get(text_field)
            if value:
                rows.append(f"<tr><th style='text-align:left;padding:4px'>{text_field.title()}</th><td style='padding:4px'>{value}</td></tr>")
        html_parts.append("<table border='1' cellspacing='0' cellpadding='2'>" + "".join(rows) + "</table>")
    return "\n".join(html_parts)


def send_email(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Send an email notification for the given records via Resend.

    If the `resend` SDK is not installed or the RESEND_API_KEY
    environment variable is missing, this function logs an error and
    returns None.

    Parameters
    ----------
    records: List[Dict[str, Any]]
        The records to include in the email.  If empty, no email is sent.

    Returns
    -------
    Optional[Dict[str, Any]]
        The result from Resend's API call, or None if email was not sent.
    """
    if not records:
        logger.info("No matching records to email; skipping send.")
        return None
    if not _RESEND_AVAILABLE:
        logger.error("Resend SDK is not installed. Cannot send email.")
        return None
    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL")
    to_email = os.environ.get("RESEND_TO_EMAIL", "kzvolsky@novis.eu")
    if not api_key or not from_email:
        logger.error("Resend API key or from email not configured.")
        return None
    resend.api_key = api_key
    subject = "NOVIS – new bankruptcy/liquidation notice"
    html_body = format_records_html(records)
    params: Dict[str, Any] = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    try:
        response = resend.Emails.send(params)  # type: ignore[attr-defined]
        logger.info("Email sent via Resend: %s", response)
        return response
    except Exception as exc:
        logger.error("Error sending email via Resend: %s", exc)
        return None


def load_last_run_timestamp(path: str) -> Optional[str]:
    """Load the ISO timestamp of the last run from a file.

    If the file does not exist, returns None.

    Parameters
    ----------
    path: str
        Path to the file containing the timestamp.

    Returns
    -------
    Optional[str]
        The timestamp string, or None.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def save_last_run_timestamp(path: str, timestamp: str) -> None:
    """Persist the ISO timestamp of the last successful run to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(timestamp)


def perform_update(
    since: str,
    query: str = "NOVIS",
    to_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Perform a full update cycle: fetch, filter and send notifications.

    Parameters
    ----------
    since: str
        ISO 8601 timestamp for retrieving changes.

    Returns
    -------
    Dict[str, Any]
        Summary containing the number of records fetched, filtered and
        whether an email was sent.
    """
    from_dt = _dt.datetime.fromisoformat(since.replace("Z", "+00:00"))
    to_dt = _dt.datetime.fromisoformat(to_timestamp.replace("Z", "+00:00")) if to_timestamp else None
    total_fetched = 0
    matched_records: List[Dict[str, Any]] = []
    for friendly_name, path in DATASETS:
        records = fetch_changes(path, since)
        total_fetched += len(records)
        records = filter_records_by_date_range(records, from_dt=from_dt, to_dt=to_dt)
        matched = filter_records_by_query(records, query=query)
        matched_records.extend(matched)
    email_result = send_email(matched_records)
    summary = {
        "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
        "since": since,
        "to": to_timestamp,
        "query": query,
        "fetched": total_fetched,
        "matches": len(matched_records),
        "email_sent": email_result is not None,
    }
    return summary


def main() -> None:
    """Entry point when running this module as a script."""
    # Determine the path for storing the last run timestamp relative to this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ts_path = os.path.join(current_dir, "last_run.txt")
    last_ts = load_last_run_timestamp(ts_path)
    if not last_ts:
        # Default to 30 days ago if there is no record of previous runs
        last_dt = _dt.datetime.utcnow() - _dt.timedelta(days=30)
        last_ts = last_dt.isoformat() + "Z"
    logger.info("Fetching updates since %s", last_ts)
    summary = perform_update(last_ts)
    logger.info(
        "Fetched %(fetched)d records, %(matches)d matched, email_sent=%(email_sent)s",
        summary,
    )
    # Save the new timestamp for next run
    save_last_run_timestamp(ts_path, summary["timestamp"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
