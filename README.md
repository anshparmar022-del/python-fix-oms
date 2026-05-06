# FIX OMS — Institutional Order Management System

A production-grade FIX 4.4 Order Management System built in Python. This system acts as a high-performance FIX acceptor that handles multiple client connections, enforces institutional risk limits, and executes trades via an internal price-time priority matching engine.

---

## 🎯 Core Functionality

- **Pure FIX 4.4 Protocol**: Industry-standard communication for New Orders (35=D), Cancels (35=F), and Replaces (35=G).
- **Multi-Client Support**: Simultaneously handles connections from `CLIENT1`, `CLIENT2`, and `QFIXMESSENGER`.
- **Pre-Trade Risk Engine**: Enforces quantity, notional, and position limits, plus **Fat Finger** price protection.
- **Matching Engine**: Price-time priority (FIFO) execution with support for partial fills.
- **Position & P&L Tracking**: Real-time calculation of net positions and realized P&L after every fill.
- **Market Data Snapshot**: Maintains live BBO (Best Bid/Offer), VWAP, volume, and daily High/Low.
- **Persistence**: Full audit trail of orders and executions stored in a local SQLite database.

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
├── log/                            ← FIX session logs (auto-created)
└── store/                          ← FIX message store (auto-created)
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
  🚀 FIX OMS — Institutional Order Management System
  ────────────────────────────────────────────────────────────────────────────
  💎 Instance      : OMS-PRODUCTION-SRV-1
  🌐 Connectivity  : FIX.4.4 | Port 5001
  🏦 Multi-Client  : ENABLED (CLIENT1, CLIENT2, QFIXMESSENGER)
  🛡️  Risk Engine  : ACTIVE
  📈 Matching      : LiquidityBook-Symbol-Routing
```

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

---

## 🛡️ Risk Management

Every order is validated against institutional-grade risk limits defined in `core/risk_engine.py`:

| Check | Limit | Description |
|---|---|---|
| Max Quantity | 10,000 | Prevents accidentally large orders |
| Max Notional | $10,000,000 | Prevents high-value exposure |
| Fat Finger | 10% Deviation | Rejects orders too far from current market price |
| Symbol Whitelist | Active | Only allows trades for approved symbols (AAPL, MSFT, etc.) |
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

The system uses **SQLite** for persistence. You can query `oms_data.db` directly or use `scripts/view_positions.py`.

| Table | Purpose |
|---|---|
| `orders` | Complete history of all orders and their current status |
| `positions` | Real-time net quantity, average cost, and realized P&L |
| `executions` | Audit trail of every individual fill event |
| `market_data` | Live snapshot of symbol statistics (BBO, VWAP, High/Low) |

---

## 🔍 Monitoring

To monitor your trading activity in real-time without a FIX client, run:
```bash
python scripts/view_positions.py
```
This will display a professional terminal dashboard showing your Live Positions, Market Data, and Recent Executions.

---

## 🛠️ Dependencies

- **quickfix==1.15.1**: Core FIX protocol engine.
- (Standard Python libraries used for all other logic to keep the system lean).
