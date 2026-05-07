import sqlite3
import threading
from datetime import datetime
import uuid

class OrderManager:
    def __init__(self, db_path="oms_data.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        # Creates tables for orders, positions, and executions
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, symbol TEXT, side TEXT, qty REAL, price REAL, status TEXT, filled_qty REAL, avg_price REAL, leaves_qty REAL, client_id TEXT, timestamp TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS positions (client_id TEXT, symbol TEXT, net_qty REAL, avg_cost REAL, realized_pnl REAL, updated_at TEXT, PRIMARY KEY(client_id, symbol))")
            conn.execute("CREATE TABLE IF NOT EXISTS executions (exec_id TEXT PRIMARY KEY, order_id TEXT, client_id TEXT, symbol TEXT, side TEXT, fill_qty REAL, fill_price REAL, timestamp TEXT)")
            conn.execute("CREATE TABLE IF NOT EXISTS market_data (symbol TEXT PRIMARY KEY, bid REAL, ask REAL, last_price REAL, last_qty REAL, volume REAL, vwap REAL, high REAL, low REAL, updated_at TEXT)")

    def add_order(self, order):
        # Persists a new order to SQLite
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (order["id"], order["symbol"], order["side"], order["qty"], order["price"],
                         order.get("status", "NEW"), order.get("filled_qty", 0), order.get("avg_price", 0),
                         order.get("leaves_qty", order["qty"]), order.get("client_id"), datetime.now().isoformat()))

    def get_order(self, order_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    def update_status(self, order_id, status):
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))

    def replace_order(self, old_id, new_id, qty, price):
        # Updates an order in the database after a replacement
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE orders SET id=?, qty=?, price=?, status='REPLACED' WHERE id=?", (new_id, qty, price, old_id))

    def get_position(self, client_id, symbol):
        # Returns current position for a client/symbol
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM positions WHERE client_id=? AND symbol=?", (client_id, symbol)).fetchone()

    def update_fill(self, order_id, cum_qty, avg_px, status, fill_qty, symbol, side, client_id):
        # Records a fill and updates order/position state
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE orders SET filled_qty=?, avg_price=?, status=?, leaves_qty=qty-? WHERE id=?", (cum_qty, avg_px, status, cum_qty, order_id))
            conn.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?)", (str(uuid.uuid4()) if 'uuid' in globals() else str(datetime.now().timestamp()), order_id, client_id, symbol, side, fill_qty, avg_px, datetime.now().isoformat()))
            self._update_position(conn, client_id, symbol, side, fill_qty, avg_px)

    def _update_position(self, conn, client_id, symbol, side, qty, price):
        # Internal logic for position and P&L tracking
        pos = conn.execute("SELECT * FROM positions WHERE client_id=? AND symbol=?", (client_id, symbol)).fetchone()
        cur_qty, cur_cost, cur_pnl = (pos[2], pos[3], pos[4]) if pos else (0.0, 0.0, 0.0)
        trade_qty = qty if str(side) == "1" else -qty
        new_qty = cur_qty + trade_qty
        new_cost, new_pnl = cur_cost, cur_pnl
        if cur_qty * trade_qty >= 0:
            if new_qty != 0: new_cost = (cur_qty * cur_cost + trade_qty * price) / new_qty
        else:
            closed_qty = min(abs(cur_qty), abs(trade_qty))
            new_pnl += closed_qty * (price - cur_cost if cur_qty > 0 else cur_cost - price)
            if new_qty != 0: new_cost = price if abs(trade_qty) > abs(cur_qty) else cur_cost
            else: new_cost = 0.0
        conn.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?)", (client_id, symbol, new_qty, new_cost, new_pnl, datetime.now().isoformat()))

    def update_market_data(self, symbol, qty, price, bid, ask):
        # Updates global market statistics for a symbol
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            m = conn.execute("SELECT * FROM market_data WHERE symbol=?", (symbol,)).fetchone()
            vol, vwap, hi, lo = (m['volume'], m['vwap'], m['high'], m['low']) if m else (0.0, 0.0, 0.0, 999999.0)
            new_vol = vol + qty
            new_vwap = (vwap * vol + price * qty) / new_vol
            conn.execute("INSERT OR REPLACE INTO market_data VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (symbol, bid, ask, price, qty, new_vol, new_vwap, max(hi, price), min(lo, price), datetime.now().isoformat()))

    def update_bbo(self, symbol, bid, ask):
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE market_data SET bid=?, ask=? WHERE symbol=?", (bid, ask, symbol))

    def get_all_positions(self, client_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM positions WHERE client_id = ?", (client_id,)).fetchall()

manager = OrderManager()
