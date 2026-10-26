const path = require('node:path');
module.exports = { apps: [{ name: 'intraday-recorder', cwd: __dirname, script: path.join(__dirname, '.venv/bin/python'), args: '-m uvicorn app:service --host 127.0.0.1 --port 5004 --no-access-log', interpreter: 'none', instances: 1, autorestart: true, env: { PORTAL_ORIGIN: process.env.PORTAL_ORIGIN || 'http://45.129.86.77' } }] };
