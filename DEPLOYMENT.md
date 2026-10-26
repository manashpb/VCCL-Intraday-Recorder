# VCCL deployment

This independent app lives in `E:\TRADING\VCCL\intraday-recorder` locally and
`/home/manash/VCCL/intraday-recorder` on VCCL. PM2 runs one Python process on
`127.0.0.1:5004`. The workspace forwards authenticated `/recorder/` requests,
including assets and APIs, retaining the prefix. The recorder independently
checks every session with `http://127.0.0.1:5001/verify` and rejects cross-origin
mutations. The existing Nginx root proxy forwards this route through workspace;
no Nginx configuration change is required.

## Installation

```sh
cd /home/manash/VCCL/intraday-recorder
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/python -m pytest -q
export PATH="$HOME/.nvm/versions/node/v22.23.4/bin:$PATH"
PORTAL_ORIGIN=http://45.129.86.77 pm2 start ecosystem.config.cjs
pm2 save
```

Deploy the matching workspace revision, run `npm run check` and `npm test`, then
restart only `trading-workspace`. Its restart invalidates existing login sessions.
Run its `deploy/verify-live.mjs` with `RECORDER_DEPLOYED=true SCALPER_DEPLOYED=true`
using Node's `--env-file=.env`; the verifier does not print credentials.

The launcher gains **Intraday Trade Recorder**. Enter the Dhan client ID and a
DhanHQ access token through **Connect Dhan**. A connection imports today's order
and trade books, polls every five seconds and streams order updates. It continues
while the browser is closed. Tokens are cleared on disconnect or service restart;
reconnect after restart or expiry. No provider token is shipped in source.

## Updates and rollback

Record both existing commit IDs and stop if either checkout has unexpected tracked
changes. Pull with `--ff-only`, install the lock file if dependencies changed,
run tests, and restart only the recorder and the workspace as needed. Keep one
worker: this version owns one recorder account and one SQLite writer.

Back up `data/` consistently with the recorder stopped, or use SQLite's backup
API. Preserve `data/account.txt`, which binds the installation to its first Dhan
account. `RECORDER_DATA_DIR` optionally selects an independent data directory.
Do not copy the reference app's private data into this deployment.

For rollback, stop/delete only `intraday-recorder`, restore the recorded workspace
revision and restart `trading-workspace`; keep recorder data for recovery. Do not
roll back other applications or their databases. Broker reads are not tested by
deployment: they require an owner-supplied valid token.
