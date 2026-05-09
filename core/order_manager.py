import sqlite3
import threading
from datetime import datetime
import uuid


class OrderManager:
    def __init__(self, db_path="oms_data.db"):
        # Initializes the OrderManager with a persistent SQLite connection
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        # Creates necessary database tables and sets WAL pragmas
        with self._lock, self.conn:
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = FULL;")
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, symbol TEXT, side TEXT, qty REAL, price REAL, status TEXT, filled_qty REAL, avg_price REAL, leaves_qty REAL, client_id TEXT, timestamp TEXT)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS positions (client_id TEXT, symbol TEXT, net_qty REAL, avg_cost REAL, realized_pnl REAL, updated_at TEXT, PRIMARY KEY(client_id, symbol))"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS executions (exec_id TEXT PRIMARY KEY, order_id TEXT, client_id TEXT, symbol TEXT, side TEXT, fill_qty REAL, fill_price REAL, timestamp TEXT)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS market_data (symbol TEXT PRIMARY KEY, bid REAL, ask REAL, last_price REAL, last_qty REAL, volume REAL, vwap REAL, high REAL, low REAL, updated_at TEXT)"
            )

    def add_order(self, order):
        # Persists a new order to the database
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    order["id"],
                    order["symbol"],
                    order["side"],
                    order["qty"],
                    order["price"],
                    order.get("status", "NEW"),
                    order.get("filled_qty", 0),
                    order.get("avg_price", 0),
                    order.get("leaves_qty", order["qty"]),
                    order.get("client_id"),
                    datetime.now().isoformat(),
                ),
            )

    def get_order(self, order_id):
        # Retrieves an order from the database by its ClOrdID
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()

    def update_status(self, order_id, status):
        # Updates the status of an existing order
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE orders SET status = ? WHERE id = ?", (status, order_id)
            )

    def replace_order(self, old_id, new_id, qty, price):
        # Updates an order's properties and ID after a successful cancel-replace
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE orders SET id=?, qty=?, price=?, status='REPLACED' WHERE id=?",
                (new_id, qty, price, old_id),
            )

    def get_position(self, client_id, symbol):
        # Retrieves the current net position for a specific client and symbol
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM positions WHERE client_id=? AND symbol=?",
                (client_id, symbol),
            ).fetchone()

    def update_fill(
        self, order_id, cum_qty, avg_px, status, fill_qty, symbol, side, client_id
    ):
        # Records an execution fill and updates the corresponding order and position states
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE orders SET filled_qty=?, avg_price=?, status=?, leaves_qty=qty-? WHERE id=?",
                (cum_qty, avg_px, status, cum_qty, order_id),
            )
            self.conn.execute(
                "INSERT INTO executions VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    order_id,
                    client_id,
                    symbol,
                    side,
                    fill_qty,
                    avg_px,
                    datetime.now().isoformat(),
                ),
            )
            self._update_position(client_id, symbol, side, fill_qty, avg_px)

    def _update_position(self, client_id, symbol, side, qty, price):
        # Calculates and updates P&L and net quantity for a client's position
        pos = self.conn.execute(
            "SELECT * FROM positions WHERE client_id=? AND symbol=?",
            (client_id, symbol),
        ).fetchone()
        cur_qty, cur_cost, cur_pnl = (
            (pos["net_qty"], pos["avg_cost"], pos["realized_pnl"])
            if pos
            else (0.0, 0.0, 0.0)
        )
        trade_qty = qty if str(side) == "1" else -qty
        new_qty = cur_qty + trade_qty
        new_cost, new_pnl = cur_cost, cur_pnl
        if cur_qty * trade_qty >= 0:
            if new_qty != 0:
                new_cost = (cur_qty * cur_cost + trade_qty * price) / new_qty
        else:
            closed_qty = min(abs(cur_qty), abs(trade_qty))
            new_pnl += closed_qty * (
                price - cur_cost if cur_qty > 0 else cur_cost - price
            )
            if new_qty != 0:
                new_cost = price if abs(trade_qty) > abs(cur_qty) else cur_cost
            else:
                new_cost = 0.0
        self.conn.execute(
            "INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?)",
            (client_id, symbol, new_qty, new_cost, new_pnl, datetime.now().isoformat()),
        )

    def update_market_data(self, symbol, qty, price, bid, ask):
        # Updates global market statistics (volume, vwap, high, low) for a symbol
        with self._lock, self.conn:
            m = self.conn.execute(
                "SELECT * FROM market_data WHERE symbol=?", (symbol,)
            ).fetchone()
            vol, vwap, hi, lo = (
                (m["volume"], m["vwap"], m["high"], m["low"])
                if m
                else (0.0, 0.0, 0.0, 999999.0)
            )
            new_vol = vol + qty
            new_vwap = (vwap * vol + price * qty) / new_vol
            self.conn.execute(
                "INSERT OR REPLACE INTO market_data VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    symbol,
                    bid,
                    ask,
                    price,
                    qty,
                    new_vol,
                    new_vwap,
                    max(hi, price),
                    min(lo, price),
                    datetime.now().isoformat(),
                ),
            )

    def update_bbo(self, symbol, bid, ask):
        # Updates the Best Bid and Offer (BBO) for a symbol
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE market_data SET bid=?, ask=? WHERE symbol=?", (bid, ask, symbol)
            )

    def get_all_positions(self, client_id):
        # Retrieves all open positions for a specific client
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM positions WHERE client_id = ?", (client_id,)
            ).fetchall()

    def get_all_symbols(self):
        # Returns a list of all distinct symbols currently in the orders table
        with self._lock:
            rows = self.conn.execute("SELECT DISTINCT symbol FROM orders").fetchall()
            return [row["symbol"] for row in rows]


manager = OrderManager()
