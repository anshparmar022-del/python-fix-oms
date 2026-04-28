# FIX OMS — Order Management System

A fully functional Order Management System built on the **FIX 4.4 protocol** using QuickFIX/Python.  
The system simulates a real trading environment with a matching engine, order lifecycle management, and a REST API.

---

## Architecture

```
┌─────────────────────────────┐        FIX 4.4 (TCP)       ┌──────────────────────────────┐
│         OMS Process         │ ◄─────────────────────────► │      Exchange Process         │
│                             │                             │                              │
│  OMSApp (FIX Initiator)     │                             │  ExchangeApp (FIX Acceptor)  │
│  REST API  :5000            │                             │  Matching Engine             │
│                             │                             │  Admin API  :5001            │
│  SQLite DB (oms_data.db)    │                             │                              │
└─────────────────────────────┘                             └──────────────────────────────┘
```

**Two independent processes** communicate exclusively over FIX protocol:

- **Exchange** (`run_exchange.py`) — accepts FIX connections, runs the matching engine, sends execution reports back to OMS. Exposes an internal admin API on port 5001 for manual fills.
- **OMS** (`run_oms_only.py`) — connects to the exchange over FIX, persists all order state to SQLite, exposes the user-facing REST API on port 5000.

---

## Features

- FIX 4.4 protocol (NewOrderSingle, ExecutionReport, OrderCancelRequest, OrderCancelReplaceRequest)
- Price-time priority matching engine with bid/ask book
- Full order lifecycle: New → Ack → Partially Filled → Filled → Canceled → Replaced
- Weighted average price calculation across multiple partial fills
- Manual fill / partial fill by ClOrdID via REST API
- Thread-safe order book with `threading.Lock`
- SQLite persistence with full order history
- Input validation and meaningful error responses on all API endpoints

---

## Setup

### Prerequisites
- Python 3.9
- QuickFIX wheel (included: `quickfix-1.15.1-cp39-cp39-win_amd64.whl`)

### Install
```bash
# Create and activate virtual environment
python -m venv .venv39
.venv39\Scripts\activate          # Windows
source .venv39/bin/activate       # Linux/Mac

# Install QuickFIX
pip install ../quickfix-1.15.1-cp39-cp39-win_amd64.whl

# Install other dependencies
pip install -r requirements.txt
```

---

## Running

Open **two terminals**, both inside the `fix_oms/` directory.

**Terminal 1 — Exchange:**
```bash
python run_exchange.py
```

**Terminal 2 — OMS + API:**
```bash
python run_oms_only.py
```

You should see:
```
🏛️  Exchange Logged ON and Session Saved: FIX.4.4:EXCHANGE_NEW->OMS_NEW
🛰️  OMS Logged ON: FIX.4.4:OMS_NEW->EXCHANGE_NEW
🌐 OMS API running on http://127.0.0.1:5000
```

---

## REST API Reference

All requests to the OMS are on `http://localhost:5000`.

### Place Order
```
POST /order
{
  "symbol": "AAPL",
  "side": "1",        // 1 = Buy, 2 = Sell
  "qty": 100,
  "price": 150.0
}
```

### Get All Orders
```
GET /orders
GET /orders?status=PARTIALLY_FILLED
GET /orders?symbol=AAPL
```

### Get Single Order
```
GET /order/<order_id>
```

### Cancel Order
```
DELETE /order/<order_id>

// or by ClOrdID:
POST /order/cancel
{ "clordid": "<order_id>" }
```

### Replace Order
```
POST /order/replace
{
  "orig_clordid": "<existing_order_id>",
  "symbol": "AAPL",
  "side": "1",
  "qty": 200,
  "price": 155.0
}
```

### View Order Book
```
GET /book
```

### Manual Fill (simulate exchange fill)
```
POST /exchange/simulate_fill
{
  "clordid": "<order_id>",
  "qty": 50,          // partial or full fill
  "price": 150.5
}
```
Call multiple times with partial quantities to simulate partial fills.  
The system automatically calculates the weighted average price across fills.

---

## Order Status Flow

```
PENDING → NEW → PARTIALLY_FILLED → FILLED
                                 → CANCELED
       → NEW → REPLACED
```

---

## Project Structure

```
fix_oms/
├── api/
│   └── server.py           # Flask REST API (OMS-facing)
├── config/
│   ├── exchange.cfg        # FIX acceptor config
│   ├── oms.cfg             # FIX initiator config
│   └── FIX44.xml           # FIX data dictionary
├── core/
│   ├── models.py           # Order dataclass and enums
│   └── order_manager.py    # SQLite persistence layer
├── fix_engine/
│   ├── exchange_app.py     # FIX acceptor app + matching engine integration
│   ├── matching_engine.py  # Thread-safe price-time priority matching engine
│   └── oms_app.py          # FIX initiator app + execution report handler
├── run_exchange.py         # Exchange process entry point
├── run_oms_only.py         # OMS process entry point
└── requirements.txt
```

---

## Key Design Decisions

**Why two separate processes?**  
In real trading systems, the exchange and OMS are always separate systems communicating over a network protocol. Running them as separate processes enforces this boundary and means the OMS has no direct memory access to the exchange — all communication goes through FIX messages, exactly as in production.

**Why SQLite?**  
Keeps the project self-contained and easy to run. In production this would be PostgreSQL or a time-series DB. The `OrderManager` class is the only place that touches the DB, so swapping it out is straightforward.

**Weighted average price**  
Each partial fill updates `avg_price` as `(prev_avg * prev_filled + last_px * last_qty) / new_filled`, matching how real brokers calculate VWAP fill price.
