# VCCL Intraday Trade Recorder

Independent VCCL feature adapted from DHAN_TRADE_RECORDER: FastAPI, SQLite and vanilla JavaScript. Open **Intraday Trade Recorder** from the shared workspace launcher at `/recorder/`. See [DEPLOYMENT.md](DEPLOYMENT.md) for installation, authentication, updates and rollback.

Run tests with `.venv` Python: `python -m pytest -q`. For local development, run the workspace login portal at port 5001, proxy `/recorder/` to port 5004, and launch `python -m uvicorn app:service --host 127.0.0.1 --port 5004` with `PORTAL_ORIGIN` matching the browser origin.

## Recording and accounting

- Imports today's `/v2/orders` and `/v2/trades` on connection. Checks both every five seconds; streams order changes over Dhan's individual order-update WebSocket with reconnect backoff.
- Persists distinct received broker payloads with capture timestamps and source. Identical payloads are deduplicated. Historical modifications before recording started, or between disconnected periods, cannot be reconstructed from the current order book. Leave the process running during market hours; there is no background Windows service yet.
- Executions are reconciled by order ID + exchange trade ID. WebSocket cumulative filled quantity is displayed but never added as another execution. Execution grouping may lag the stream by the reconciliation interval.
- Filters journal views to INTRADAY, NSE_FNO/BSE_FNO, NIFTY/SENSEX option symbols. BANKNIFTY and other indices are excluded. Captures all account order events in the recorder database to allow later investigation.
- One automatic trade per trading day, exchange, and security, from flat to flat. Quantity-level FIFO realizes P&L, supports shorts, scaling, partial exits and reversals. A reversal fill is split between its closing and opening trades. Quantities are broker units, not lots. Monetary math uses Decimal; P&L is gross and excludes brokerage/taxes. No unrealized P&L without market quotes.
- Drag any order onto a trade or select it to assign a default exit purpose, trade collection and notes. These persistent order-level journal annotations do not rewrite execution-level FIFO accounting. This preserves reversal splits. Custom collections are named in browser local storage; their order assignments and notes are persisted in SQLite. Manual collection P&L, quantity-level reassignment, multi-contract strategies, and split/merge accounting are future enhancements.
- Stop-order types suggest stop-loss purpose in the editor; broker target leg metadata suggests target. These remain editable suggestions and are not evidence that the order belongs to a particular trade. Choose a trade and save to confirm. Pending/cancelled protection orders can also be assigned. SL/target prices appear on cards after assignment; their recorded changes are visible in order history.

## Position effect and exit purpose

Click an order in a trade or the order tray to open its editor. The old single **Order role** dropdown has been replaced by separate calculated effects and editable purposes.

| Concept | Values | How it works |
| --- | --- | --- |
| Position effect | Entry, Exit, Reversal, Unfilled | Calculated from reconciled execution quantities; cannot be edited |
| Default exit purpose | Stop loss, Target, Discretionary, Unknown | Journal annotation applied to the order's closing allocations |
| Allocation exit purpose | Use order default, Stop loss, Target, Discretionary, Unknown | Optional override for one closing fill within one automatic trade |
| Stop adjustment | Stop adjusted to breakeven | Optional stop-loss annotation; does not change accounting or broker prices |

**Partial exits:** Buying 65 units and selling 25 at a target produces an Exit / Target allocation for 25 units, leaving 40 units open. The FIFO details display “partial exit” and remaining units. Partial exit is a quantity outcome, not a purpose.

**Reversals:** Selling 100 units against a 65-unit long position creates a closing allocation of 65 and a new short entry of 35. The editor shows Reversal, Entry 35 and Exit 65. Exit purpose and breakeven annotations apply only to the closing allocation; the opening allocation has no exit purpose.

**Mixed purposes:** If an order has multiple closing fills, expand its editor's **Exit execution allocations**. One fill may use Target and another Discretionary or Stop loss. Choose **Use order default** to remove an override. Overrides use automatic trade ID + broker fill ID and are stored in SQLite. This version classifies each existing closing allocation; it does not subdivide a single closing fill into arbitrary user-selected quantities.

**Breakeven:** Set purpose to Stop loss and tick **Stop adjusted to breakeven**. This is your annotation about stop management, not an inference that an execution was profitable or net zero. Broker trigger/limit histories and manual planned-level histories retain the actual price changes separately. Slippage, fees and scaling can make realized P&L differ from zero.

**Unfilled orders:** A pending or cancelled order with no fills displays Unfilled. Its purpose can still be Stop loss or Target, and its modification history remains available. A partially filled order displays the effect of its executed quantity alongside its unfilled remainder.

Purposes resolve in this order: explicit allocation override, saved order default, linked broker-purpose suggestion, Unknown. Suggestions are labelled in FIFO details. An explicit Unknown overrides a suggestion. Existing Stop/Target role annotations are read as equivalent purposes; old Entry/Exit/Unassigned roles become Unknown because position effect is calculated independently. Existing trade collection assignments and notes are preserved. Saving through the new editor stores the new schema; no destructive migration is needed.

The **Trade** selector controls the journal collection and confirmed protection link. It does not change execution allocations or FIFO P&L. For reversals, all closing allocations are available in the editor even when the order is displayed under another journal collection.

## Storage and access

`data/journal.sqlite3` stores events, normalized orders, fills, order defaults, allocation overrides, and planned-level histories. Back up the database with the server stopped, including WAL files if present. `data/account.txt` binds this journal to the first connected client ID using a hash. Use a separate installation/data directory for another account.

Keep the backend bound to loopback. The shared VCCL login protects pages, assets and APIs, and the backend independently verifies each session. Mutations require the configured workspace origin. No token is stored in the database or browser storage. Trade records are sensitive server data. Closing the browser does not stop the recorder; stopping the Python process does.

## Planned SL/target and broker protection history

Each automatic trade has **Edit planned SL / target**. Either price may be left blank; no broker order is required. Changes and optional reasons are appended to SQLite history, including clearing a price. These are option premium prices, not underlying index levels.

Linked SL/target orders display their captured limit/trigger prices, statuses, times and source. Manual order exit-purpose assignments confirm a link. Explicit broker leg metadata or stop-order types can suggest a link when contract, exit side and trade timing uniquely match; ambiguous orders remain unlinked. Regular limit orders require manual target assignment. Planned levels and broker levels remain separate, and cancelled/filled orders retain history rather than being shown as active protection. Earlier modifications before recording started cannot be recovered.

## Validation commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Official broker references: [Order update protocol](https://dhanhq.co/docs/v2/order-update/), [Orders and trade book](https://dhanhq.co/docs/v2/orders/).
