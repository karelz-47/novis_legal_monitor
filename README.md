# Legal Monitor

This project provides a small utility that periodically queries public
APIs from [Ekosystém Slovensko.Digital](https://ekosystem.slovensko.digital/)
for new submissions relating to bankruptcies, restructurings and
liquidations.  It filters the results for companies whose names
contain a user-provided search query and sends an email notification
whenever such records appear.

## Data sources

The Slovensko.Digital data hub exposes several endpoints under the
`ov` (Obchodný vestník) namespace.  We use the following endpoints
documented on the *Otvorené API* page:

| Dataset | Purpose | Endpoint | Notes |
|-------|---------|----------|------|
| **konkurz_restrukturalizacia_issues** | Bankruptcy/restructuring proposals | `GET …/ov/konkurz_restrukturalizacia_issues/:id` with a synchronisation variant `…/ov/konkurz_restrukturalizacia_issues/sync` | The API returns details about court proposals for bankruptcy or restructuring, including debtor information, proposers and headings【333368336233229†L687-L768】. |
| **konkurz_vyrovnanie_issues** | Progress in bankruptcy/settlement proceedings | `GET …/ov/konkurz_vyrovnanie_issues/:id` | Records include the corporate body name and a description of the announcement【333368336233229†L770-L799】. |
| **likvidator_issues** | Liquidator submissions | `GET …/ov/likvidator_issues/:id` with a synchronisation variant `…/ov/likvidator_issues/sync` | Returns announcements from liquidators, including the corporate body name and other details such as the court and decision dates【333368336233229†L866-L927】. |

All of these datasets support a synchronisation endpoint (the `/sync`
suffix) that accepts a `since` timestamp and returns only records
created or updated after the given ISO‑8601 time.  When more than one
page of results is available, the response includes a `Link` header
pointing to the next page【333368336233229†L762-L768】.

## Components

### `monitor.py`

This module contains the core logic:

* **`fetch_changes`** — calls the `/sync` endpoint for a dataset,
  follows pagination via the `Link` header and returns a list of
  records.
* **`fetch_items_from_last_n_days`** — helper that fetches all items
  from a given dataset for the last *n* days.
* **`record_contains_novis`** — inspects a record and checks
  whether the debtor’s or corporate body name contains `NOVIS`.
* **`filter_records_for_novis`** — filters a list of records to those
  relevant to the query.
* **`send_email`** — uses the [Resend Python SDK](https://resend.com/docs/send-with-python) to send a formatted HTML email
  summarising the matching records.  API credentials are read from
  environment variables.
* **`perform_update`** — orchestrates the whole update: fetches
  changes since a timestamp, filters them and triggers an email
  notification.

When executed directly (`python monitor.py`), the module reads a
timestamp from `last_run.txt`, defaults to 30 days ago if missing,
runs an update and saves the current timestamp back to the file.

### `streamlit_app.py`

Provides a minimal web interface using [Streamlit](https://streamlit.io/):

* Shows the time of the last update run.
* Offers a **Run update** button to trigger a manual check.
* Displays a JSON summary of the run, including how many records were
  fetched and how many matched.

To launch the app:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### `requirements.txt`

Lists the Python dependencies: `requests`, `resend` and `streamlit`.

## Configuration

The monitor uses the Resend email service.  Before running it you
must set the following environment variables:

* **`RESEND_API_KEY`** – Your Resend API key.
* **`RESEND_FROM_EMAIL`** – A verified email address within your
  Resend account.  The email will appear to be sent from this
  address.
* **`RESEND_TO_EMAIL`** – (Optional) Destination address.  Defaults
  to `kzvolsky@novis.eu` if unset.

On each update the monitor saves the current UTC timestamp to
`last_run.txt`.  Subsequent runs use this timestamp to
request only new or modified records via the `since` parameter.

## Scheduling

The project does not include a built‑in scheduler to avoid blocking
the Streamlit interface.  Deployments are expected to schedule the
update task using external tools such as `cron`, `systemd` timers or
task queues.  For example, to run the monitor every hour you could
add a cron job like:

```cron
0 * * * * /usr/bin/env bash -c \
  'cd /path/to/legal_monitor && \n+   RESEND_API_KEY=your_key RESEND_FROM_EMAIL=your_from \n+   RESEND_TO_EMAIL=your_to python monitor.py >> monitor.log 2>&1'
```

## Limitations

* The Slovensko.Digital API is rate‑limited and may return multiple
  pages of results.  The monitor follows the `Link` header but stops
  when an error status is encountered.
* Records that contain `NOVIS` in a different field (e.g. nested
  within free‑form text) are not detected.  Only debtor names,
  proposers’ names and top‑level corporate names are checked.
* The application sends plain HTML emails; no attachments or rich
  formatting beyond simple tables are included.  Resend domain
  verification is required before emails can be delivered.

## License

This example is provided for educational purposes and does not
constitute legal advice.  Use at your own risk.