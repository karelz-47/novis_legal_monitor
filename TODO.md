# NOVIS Monitor – Setup TODO

- [ ] Create and activate a Python 3.13 virtual environment.
- [ ] Install dependencies with `pip install -r requirements.txt`.
- [ ] Set required environment variables:
  - `RESEND_API_KEY`
  - `RESEND_FROM_EMAIL`
  - `RESEND_TO_EMAIL` (optional, defaults in code)
- [ ] Run a local syntax check: `python -m py_compile monitor.py streamlit_app.py`.
- [ ] Run one dry monitor cycle from CLI: `python monitor.py` and confirm no runtime errors.
- [ ] Start the Streamlit UI: `streamlit run streamlit_app.py`.
- [ ] In the UI, click **Run update** and verify:
  - last run timestamp updates,
  - summary JSON appears,
  - email is received when matching NOVIS records exist.
- [ ] Add deployment scheduler (cron/systemd) for periodic monitoring.
- [ ] Configure logging destination (file or central logging) for production diagnostics.
