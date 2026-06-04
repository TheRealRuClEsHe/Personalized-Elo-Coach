"""
EloCoach — Export GA4 feedback_submitted events to Google Sheets
================================================================
SETUP (one-time, ~10 min):
  1. Go to https://console.cloud.google.com/ → create or select a project
  2. Enable these two APIs:
       - Google Analytics Data API
       - Google Sheets API
  3. Create a Service Account → download the JSON key → save as:
       Personalized-Elo-Coach/secrets/ga_service_account.json
  4. In GA4 Admin → Property → Custom definitions → Custom dimensions,
     register these four event-scoped dimensions:
       - rating        (parameter name: rating)
       - reason        (parameter name: reason)
       - comment       (parameter name: comment)
       - win_probability (parameter name: win_probability)
     Without this step, GA4 will NOT return the parameter values.
  5. Share your Google Sheet with the service account email
     (found in the JSON key as "client_email") — give it Editor access.
  6. pip install google-analytics-data google-auth gspread

USAGE:
  python scripts/export_feedback_to_sheets.py

  Set SHEET_ID and GA4_PROPERTY_ID below before running.
"""

import json
import logging
from datetime import datetime

import gspread
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    Metric,
    RunReportRequest,
)
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────
SERVICE_ACCOUNT_FILE = "secrets/ga_service_account.json"

# GA4 numeric property ID — find it in GA4 Admin → Property Settings
# (NOT the G-XXXXXXXX measurement ID — it's a plain number like 123456789)
GA4_PROPERTY_ID = "YOUR_GA4_PROPERTY_ID"

# Google Sheet ID — the long string in the sheet URL:
# https://docs.google.com/spreadsheets/d/<THIS_PART>/edit
SHEET_ID = "YOUR_GOOGLE_SHEET_ID"
SHEET_TAB = "Feedback"  # Tab name to write to (created if missing)

# Date range to pull (YYYY-MM-DD or "today", "yesterday", "NdaysAgo")
DATE_START = "2026-01-01"
DATE_END   = "today"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


def fetch_feedback_from_ga4() -> list[dict]:
    """Pull feedback_submitted events from GA4 Data API."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = BetaAnalyticsDataClient(credentials=creds)

    request = RunReportRequest(
        property=f"properties/{GA4_PROPERTY_ID}",
        dimensions=[
            Dimension(name="date"),
            Dimension(name="sessionDefaultChannelGroup"),
            # Custom dimensions — must be registered in GA4 Admin first
            Dimension(name="customEvent:rating"),
            Dimension(name="customEvent:reason"),
            Dimension(name="customEvent:comment"),
            Dimension(name="customEvent:win_probability"),
        ],
        metrics=[
            Metric(name="eventCount"),
        ],
        date_ranges=[DateRange(start_date=DATE_START, end_date=DATE_END)],
        dimension_filter=FilterExpression(
            filter=Filter(
                field_name="eventName",
                string_filter=Filter.StringFilter(value="feedback_submitted"),
            )
        ),
        limit=10000,
    )

    try:
        response = client.run_report(request)
    except Exception as e:
        log.error(f"GA4 API call failed: {e}")
        raise

    rows = []
    for row in response.rows:
        dims = [d.value for d in row.dimension_values]
        rows.append({
            "date":            dims[0],
            "channel":         dims[1],
            "rating":          dims[2],
            "reason":          dims[3],
            "comment":         dims[4],
            "win_probability": dims[5],
            "event_count":     row.metric_values[0].value,
        })

    log.info(f"Fetched {len(rows)} rows from GA4.")
    return rows


def write_to_sheets(rows: list[dict]) -> None:
    """Write rows to Google Sheets, creating the tab if needed."""
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SHEET_ID)

    # Get or create the tab
    try:
        ws = sh.worksheet(SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_TAB, rows=1000, cols=10)
        log.info(f"Created new tab: {SHEET_TAB}")

    # Clear and rewrite (full refresh)
    ws.clear()

    headers = ["Date", "Channel", "Rating", "Reason", "Comment", "Win Probability", "Event Count", "Exported At"]
    exported_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    data = [headers]
    for r in rows:
        data.append([
            r["date"],
            r["channel"],
            r["rating"],
            r["reason"],
            r["comment"],
            r["win_probability"],
            r["event_count"],
            exported_at,
        ])

    ws.update(data, "A1")
    log.info(f"Written {len(rows)} rows to '{SHEET_TAB}' tab in Google Sheet.")


def main():
    if GA4_PROPERTY_ID == "YOUR_GA4_PROPERTY_ID":
        raise ValueError("Set GA4_PROPERTY_ID in this script before running.")
    if SHEET_ID == "YOUR_GOOGLE_SHEET_ID":
        raise ValueError("Set SHEET_ID in this script before running.")

    rows = fetch_feedback_from_ga4()
    if not rows:
        log.warning("No feedback_submitted events found in the date range.")
        return
    write_to_sheets(rows)
    log.info("Done.")


if __name__ == "__main__":
    main()
