# Intraday recorder

- Independent FastAPI/SQLite application derived from the local Dhan recorder.
- Public prefix `/recorder/`; production listener is loopback 5004, one worker.
- Every resource verifies `trading_session` with the workspace on loopback 5001.
- Mutations require an exact configured `PORTAL_ORIGIN`. Never add broker writes.
- Keep tokens in memory. Never commit credentials, data, or the source recorder's database.
- Run `.venv` Python with `-m pytest -q` and `node --check static/app.js`.
- Existing FIFO accounting and exit-purpose distinctions must remain intact.
