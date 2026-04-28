import sqlite3
from datetime import datetime

class OrderManager:
    def __init__(self, db_path="oms_data.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                (id TEXT PRIMARY KEY, symbol TEXT, side TEXT, qty REAL, price REAL, 
                 status TEXT, filled_qty REAL, avg_price REAL, timestamp TEXT)''')
            conn.commit()

    def add_order(self, order):
        order.update({'status': 'PENDING', 'filled_qty': 0, 'avg_price': 0, 'timestamp': datetime.now().isoformat()})
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", 
                (order['id'], order['symbol'], order['side'], order['qty'], order['price'], 
                 order['status'], order['filled_qty'], order['avg_price'], order['timestamp']))
            conn.commit()
        return order

    # Inside core/order_manager.py

    def update_status(self, clord_id, status):
    # Map FIX codes to human-readable labels
        status_map = {"0": "NEW", "1": "PARTIALLY_FILLED", "2": "FILLED", "4": "CANCELED", "5": "REPLACED" , "8": "REJECTED"}
        readable = status_map.get(status, status)
    
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE orders SET status = ? WHERE id = ?', (readable, clord_id))
            conn.commit()

    def update_fill(self, clord_id, cum_qty, avg_px, status):
        # FIX Protocol mapping
        status_map = {"1": "PARTIALLY_FILLED", "2": "FILLED"}
        readable_status = status_map.get(str(status), "FILLED" if float(cum_qty) > 0 else "NEW")

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE orders SET filled_qty = ?, avg_price = ?, status = ? WHERE id = ?
            ''', (cum_qty, avg_px, readable_status, clord_id))
            conn.commit()

    def get_order(self, order_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE id=?", (order_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_orders(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY timestamp DESC")
            return [dict(row) for row in cursor.fetchall()]
        
    def replace_order(self, old_id, new_id, new_qty, new_px):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.cursor()
            
            # Convert to float to be safe
            n_qty = float(new_qty)
            n_px = float(new_px)

            # If the FIX message provided the new data, update everything
            if n_qty > 0 and n_px > 0:
                cursor.execute("""
                    UPDATE orders 
                    SET id = ?, qty = ?, price = ?, status = 'REPLACED' 
                    WHERE id = ?
                """, (new_id, n_qty, n_px, old_id))
            else:
                # If fields were missing, just update the ID and Status
                cursor.execute("""
                    UPDATE orders 
                    SET id = ?, status = 'REPLACED' 
                    WHERE id = ?
                """, (new_id, old_id))
            conn.commit()

manager = OrderManager()