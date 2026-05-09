# FIX OMS — Institutional Order Management System

A production-grade FIX 4.4 Order Management System built in Python. This system acts as a high-performance FIX acceptor that handles multiple client connections, enforces institutional risk limits, and executes trades via an internal price-time priority matching engine.

---

## 🎯 Core Functionality

- **Pure FIX 4.4 Protocol**: Industry-standard communication for New Orders (35=D), Cancels (35=F), and Replaces (35=G).
- **Multi-Client Support**: Simultaneously handles connections from `CLIENT1`, `CLIENT2`, and `QFIXMESSENGER`.
- **Pre-Trade Risk Engine**: Enforces quantity, notional, and position limits, plus **Fat Finger** price protection.
- **Matching Engine**: Price-time priority (FIFO) execution with support for partial fills and Time-In-Force (IOC/FOK).
- **Position & P&L Tracking**: Real-time calculation of net positions and realized P&L after every fill.
- **Smart Reporting**: Filtered position reporting (active balances only) to optimize message flow and network buffers.
- **Market Data Snapshot**: Maintains live BBO (Best Bid/Offer), VWAP, volume, and daily High/Low.
- **Persistence**: Full audit trail of orders and executions stored in a local SQLite database.

---

## ⚡ High-Performance Architecture

- **LMAX-Inspired Single Writer**: Decouples QuickFIX C++ networking threads from the Python execution environment using a nanosecond lock-free `queue.Queue`. A dedicated single-writer thread handles all matching and persistence, completely eliminating database lock contention.
- **Write-Ahead Logging (WAL)**: The SQLite database operates in WAL mode with `synchronous = FULL`, enabling high-concurrency read/writes while guaranteeing absolute durability for institutional transaction integrity.
- **Deterministic Shutdown**: Implements a 'Poison Pill' sentinel pattern to guarantee the matching engine strictly drains the queue and shuts down cleanly without hanging or losing in-flight trades.

---

## 🏗️ Project Structure

```
fix_oms_final_build/
├── run_oms.py                      ← Entry point — starts the FIX acceptor
├── requirements.txt                ← Project dependencies
├── config/
│   ├── oms.cfg                     ← FIX session configuration (Port 5001)
│   └── FIX44.XML                   ← FIX 4.4 Data Dictionary
├── core/
│   ├── order_manager.py            ← SQLite persistence and position tracking
│   ├── risk_engine.py              ← Pre-trade validation & Fat Finger checks
│   └── models.py                   ← Data models and status enums
├── fix_engine/
│   ├── oms_app.py                  ← Main FIX application (Message Routing)
│   ├── matching_engine.py          ← Order matching and fill logic
│   ├── liquidity_book.py           ← Per-symbol in-memory order books
│   └── fix_mapper.py               ← FIX message field extraction
├── scripts/
│   └── view_positions.py           ← Terminal utility to monitor live P&L
```

---

## 🚀 Setup & Execution

**Prerequisites:** Python 3.9+ and the QuickFIX library.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the OMS
python run_oms.py
```

Upon startup, the terminal will display the active modules:
```
  FIX OMS — Institutional Order Management System
  Instance      : OMS-PRODUCTION-SRV-1
  Connectivity  : FIX.4.4 | Port 5001
  Multi-Client  : ENABLED (CLIENT1, CLIENT2, QFIXMESSENGER)
  Risk Engine  : ACTIVE
  Matching      : LiquidityBook-Symbol-Routing
```

> **Adding a new client:** Add a new `[SESSION]` block to `config/oms.cfg` with the desired `TargetCompID`. No code changes required. A ready-to-use initiator config is provided at `config/client.cfg`.

---

## 📡 Supported FIX Messages

### Incoming (Client → OMS)

| MsgType | Name | Description |
|---|---|---|
| 35=D | New Order Single | Enter a new limit order |
| 35=F | Order Cancel Request | Cancel an active order |
| 35=G | Order Cancel/Replace | Modify price or quantity of an active order |
| 35=q | Order Mass Cancel | Cancel all orders for a symbol or client |
| 35=AN | Request For Positions | Request a snapshot of current positions |

### Outgoing (OMS → Client)

| MsgType | Name | Trigger |
|---|---|---|
| 35=8 | Execution Report | Sent for ACK, Fill, Cancel, Replace, or Reject |
| 35=9 | Order Cancel Reject | Sent if a cancel or replace request fails |
| 35=r | Order Mass Cancel Report | Confirmation of bulk cancellations |
| 35=AP | Position Report | Snapshot of net positions and realized P&L |

---

## 🔄 Order Lifecycle

```
Client sends 35=D
       ↓
Risk Engine Check (Qty, Price, Notional, Fat Finger)
       ↓ [Fail]               ↓ [Pass]
35=8 REJECTED          35=8 NEW (ACK) sent to client
                              ↓
                     Matching Engine processes order
                     ↓ [Match Found]       ↓ [No Match]
                35=8 FILL sent         Order queued in book
                Position updated       (Wait for counterpart)
                Market Data updated
```

> [!NOTE]
> **Sequential Integrity**: The system guarantees that a "New Order ACK" always precedes a "Fill" report, ensuring true institutional protocol compliance for all downstream consumers.
> **Time-In-Force**: The engine fully respects Day, IOC, and FOK instructions, dropping orders or partial fills immediately upon constraint violation.
> **Smart Position Reporting**: Only non-zero balance symbols are pushed to clients, drastically reducing network noise during high-volume sessions.


---

## 🛡️ Risk Management

Every order is validated against institutional-grade risk limits defined in `core/risk_engine.py`:

| Check | Limit | Description |
|---|---|---|
| Max Quantity | 10,000 | Prevents accidentally large orders |
| Max Notional | $10,000,000 | Prevents high-value exposure |
| Fat Finger | 10% Deviation | Rejects orders too far from current market price |
| Position Limit | 500,000 | Limits net exposure per symbol per client |

---

## 📈 Order Matching Logic

The matching engine follows **Price-Time Priority (FIFO)**:
1.  **Bids** are sorted by highest price first.
2.  **Asks** are sorted by lowest price first.
3.  Orders at the same price are matched based on the time they were received.
4.  **IOC/FOK Support**: The system correctly handles Immediate-or-Cancel and Fill-or-Kill instructions.

---

## 📊 Database Schema

The system uses **SQLite** for persistence. You can query the database directly or use `scripts/view_positions.py`.

| Table | Purpose |
|---|---|
| `orders` | Complete history of all orders and their current status |
| `positions` | Real-time net quantity, average cost, and realized P&L |
| `executions` | Audit trail of every individual fill event |
| `market_data` | Live snapshot of symbol statistics (BBO, VWAP, High/Low) |

> [!WARNING]
> The in-memory order book resets on every OMS restart. Active orders from a previous session will still appear in the database with `NEW` or `PARTIALLY_FILLED` status, but the matching engine will not be aware of them until they are re-submitted. Plan for this in any production deployment.

---

## 🔍 Monitoring

To monitor your trading activity in real-time without a FIX client, run:
```bash
python scripts/view_positions.py
```
This will display a professional terminal dashboard showing your Live Positions, Market Data, and Recent Executions.

---

## 🏷️ FIX Tag Reference

Common tags used throughout the system:

| Tag | Name | Values |
|---|---|---|
| 35 | MsgType | D=New Order, F=Cancel, G=Replace, q=MassCancel, 8=ExecReport, 9=CancelReject, r=MassCancelReport, AN=PositionRequest, AP=PositionReport |
| 11 | ClOrdID | Unique order ID assigned by the client |
| 41 | OrigClOrdID | The ClOrdID of the order being cancelled or replaced |
| 49 | SenderCompID | Who sent the message (e.g. CLIENT1) |
| 54 | Side | 1=Buy, 2=Sell |
| 55 | Symbol | Instrument ticker (e.g. AAPL) |
| 38 | OrderQty | Number of shares |
| 44 | Price | Limit price |
| 59 | TimeInForce | 0=Day, 3=IOC, 4=FOK |
| 39 | OrdStatus | 0=New, 1=PartialFill, 2=Filled, 4=Canceled, 5=Replaced, 8=Rejected |
| 150 | ExecType | 0=New, F=Trade, 4=Canceled, 5=Replaced, 8=Rejected |
| 14 | CumQty | Total quantity filled so far |
| 151 | LeavesQty | Quantity still open |
| 6 | AvgPx | Average fill price |
| 58 | Text | Reject reason or informational message |
| 533 | TotalAffectedOrders | Number of orders cancelled in a MassCancel |

---

## 🛠️ Dependencies

- **quickfix==1.15.1**: Core FIX protocol engine.