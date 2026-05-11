# FIX OMS — Institutional Order Management System

A production-grade FIX 4.4 Order Management System built in Python. This system acts as a high-performance FIX acceptor that handles multiple client connections, enforces institutional risk limits, and executes trades via an internal price-time priority matching engine.

---

## 🎯 What It Does
- **Multi-Client Support**: Simultaneously handles connections from `CLIENT1`, `CLIENT2`, and `QFIXMESSENGER`.
- **Message Routing**: Supports New Order (35=D), Cancel (35=F), Replace (35=G), and Mass Cancel (35=q).
- **Pre-Trade Risk Engine**: Enforces quantity, notional, and position limits, plus **Fat Finger** price protection.
- **Matching Engine**: True **Price-Time Priority (FIFO)** execution with support for partial fills and Time-In-Force (IOC/FOK).
- **Position & P&L Tracking**: Real-time calculation of net positions and realized P&L after every fill.
- **Market Data Snapshot**: Maintains live BBO (Best Bid/Offer), VWAP, volume, and daily High/Low.
- **Persistence**: Full audit trail of orders and executions stored in a high-performance SQLite database.

---

## 🏗️ Project Structure
```
python-fix-oms/
├── run_oms.py                      ← Entry point — starts the FIX acceptor
├── requirements.txt                ← Project dependencies
├── config/
│   ├── oms.cfg                     ← FIX session configuration (Port 5001)
│   ├── client.cfg                  ← Initiator config for CLIENT1
│   ├── client2.cfg                 ← Initiator config for CLIENT2
│   └── FIX44.XML                   ← FIX 4.4 Data Dictionary
├── core/
│   ├── order_manager.py            ← Repository layer — SQLite persistence
│   ├── risk_engine.py              ← Pre-trade validation & Fat Finger checks
│   └── models.py                   ← Data models and status enums
├── fix_engine/
│   ├── oms_app.py                  ← Main FIX application (Message Routing)
│   ├── matching_engine.py          ← Order matching and fill logic
│   ├── liquidity_book.py           ← Per-symbol in-memory order books (FIFO)
│   └── fix_mapper.py               ← FIX message field extraction
├── scripts/
│   └── view_positions.py           ← Terminal utility to monitor live P&L
```

---

## 🚀 Setup & Execution

**Requirements:** Python 3.9+

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the OMS
python run_oms.py
```

---

## 📡 Message Protocol

### Incoming (from Client → OMS)
| MsgType | Name | Description |
|---|---|---|
| 35=D | New Order Single | Enter a new limit order |
| 35=F | Order Cancel Request | Cancel an active order |
| 35=G | Order Cancel/Replace | Modify price or quantity of an active order |
| 35=q | Order Mass Cancel | Cancel all orders for a symbol or client |
| 35=AN | Request For Positions | Request a snapshot of current positions |

### Outgoing (from OMS → Client)
| MsgType | Name | When sent |
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

| Check | Default Limit | Description |
|---|---|---|
| Max Quantity | 10,000 | Prevents accidentally large orders |
| Max Notional | $10,000,000 | Prevents high-value exposure |
| Fat Finger | 10% Deviation | Rejects orders too far from market price |
| Position Limit | 500,000 | Limits net exposure per symbol per client |

---

## 📊 Database Snapshot
The system uses **SQLite** with WAL mode for high-performance persistence.

| Table | Purpose |
|---|---|
| `orders` | Complete history of all orders and their current status |
| `positions` | Real-time net quantity, average cost, and realized P&L |
| `executions` | Audit trail of every individual fill event |
| `market_data` | Live snapshot of symbol statistics (BBO, VWAP, High/Low) |

> [!NOTE]
> **Performance Choice**: This system avoids heavy ORMs like SQLAlchemy. Raw SQL + WAL mode provides significantly lower latency, critical for institutional matching engines.

---

## 🔍 Monitoring
To monitor your trading activity in real-time, run:
```bash
python scripts/view_positions.py
```

---

## 🏷️ FIX Tag Reference
| Tag | Name | Values |
|---|---|---|
| 35 | MsgType | D=New, F=Cancel, G=Replace, q=MassCancel, 8=ExecReport, 9=CancelReject, r=MassCancelReport, AN=PositionRequest, AP=PositionReport |
| 11 | ClOrdID | Unique order ID assigned by the client |
| 41 | OrigClOrdID | The ClOrdID of the order being cancelled or replaced |
| 49 | SenderCompID | Who sent the message (e.g. CLIENT1) |
| 54 | Side | 1=Buy, 2=Sell |
| 55 | Symbol | Instrument ticker (e.g. AAPL) |
| 38 | OrderQty | Number of shares |
| 44 | Price | Limit price |
| 59 | TimeInForce | 0=Day, 3=IOC, 4=FOK |
| 39 | OrdStatus | 0=New, 1=PartFill, 2=Filled, 4=Canceled, 5=Replaced, 8=Rejected |
| 150 | ExecType | 0=New, F=Trade, 4=Canceled, 5=Replaced, 8=Rejected |
| 14 | CumQty | Total quantity filled so far |
| 151 | LeavesQty | Quantity still open |
| 6 | AvgPx | Average fill price |
| 58 | Text | Reject reason or informational message |
| 453 | NoPartyIDs | Count of parties in repeating group |
| 448 | PartyID | Party identifier string |
| 452 | PartyRole | 1=Broker, 3=Client, 11=Trader |
| 530 | MassCancelRequestType | 1=Symbol, 7=All |
| 533 | TotalAffectedOrders | Number of orders affected |

---

## 🛠️ Dependencies
- **quickfix==1.15.1**: Core FIX protocol engine.