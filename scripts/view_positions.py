import sqlite3
import os

# Updated to find the database in the parent directory
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "oms_data.db")


def hr(char="-", width=70):
    print(char * width)


def display():
    # Reads and displays all trading data from the SQLite database
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {os.path.abspath(DB_PATH)}")
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        hr("=")
        print("  [LIVE POSITIONS]")
        hr("=")
        rows = conn.execute(
            "SELECT * FROM positions ORDER BY client_id, symbol"
        ).fetchall()
        for r in rows:
            qty = float(r["net_qty"])
            print(
                f"  {'BUY' if qty>0 else 'SELL' if qty<0 else 'FLAT'} {r['client_id']:<12} {r['symbol']:<10} {qty:>+10.0f} avg={float(r['avg_cost']):>10.4f} pnl={float(r['realized_pnl']):>+10.2f}"
            )

        print("\n  [MARKET DATA]")
        hr("=")
        for r in conn.execute("SELECT * FROM market_data ORDER BY symbol").fetchall():
            print(
                f"  {r['symbol']:<10} {float(r['last_price']):>8.4f} bid={float(r['bid']):>8.4f} ask={float(r['ask']):>8.4f} vol={float(r['volume']):>10.0f}"
            )

        print("\n  [RECENT EXECUTIONS]")
        hr("=")
        for r in conn.execute(
            "SELECT * FROM executions ORDER BY timestamp DESC LIMIT 10"
        ).fetchall():
            print(
                f"  {r['order_id']:<18} {r['symbol']:<8} {'BUY' if str(r['side'])=='1' else 'SELL':<6} {float(r['fill_qty']):>10.0f} @ {float(r['fill_price']):>10.4f}"
            )

        print("\n  [OPEN ORDERS]")
        hr("=")
        for r in conn.execute(
            "SELECT * FROM orders WHERE status IN ('NEW','PARTIALLY_FILLED')"
        ).fetchall():
            print(
                f"  {r['id']:<18} {r['symbol']:<8} {float(r['qty']):>8.0f} filled={float(r['filled_qty']):>8.0f} @ {float(r['price']):>10.4f} [{r['status']}]"
            )
        hr("=")


if __name__ == "__main__":
    display()
