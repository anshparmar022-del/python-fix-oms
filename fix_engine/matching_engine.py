import threading
import logging
from typing import Optional
from datetime import datetime
from fix_engine.liquidity_book import liquidity_manager

logger = logging.getLogger("OMS_SYSTEM")


class MatchingEngine:
    def __init__(self):
        self._lock = threading.Lock()

    def match_order(self, new_order: dict, dry_run: bool = False) -> list:
        # Matches an incoming order against the resting liquidity book
        with self._lock:
            matches, sym, side, px, rem = (
                [],
                new_order["symbol"],
                str(new_order["side"]),
                float(new_order["price"]),
                float(new_order["qty"]),
            )
            book = liquidity_manager.get_book(sym)
            opp = book.asks if side == "1" else book.bids
            opp_match = list(opp) if dry_run else opp

            i = 0
            while i < len(opp_match) and rem > 0:
                maker = opp_match[i]
                if (side == "1" and px < float(maker["price"])) or (
                    side == "2" and px > float(maker["price"])
                ):
                    break

                m_qty, f_px = min(rem, float(maker["qty"])), float(maker["price"])
                b_id, s_id, b_cid, s_cid = (
                    (
                        new_order["id"],
                        maker["id"],
                        new_order.get("client_id", "K"),
                        maker.get("client_id", "K"),
                    )
                    if side == "1"
                    else (
                        maker["id"],
                        new_order["id"],
                        maker.get("client_id", "K"),
                        new_order.get("client_id", "K"),
                    )
                )

                matches.append(
                    {
                        "buy_id": b_id,
                        "sell_id": s_id,
                        "buy_client_id": b_cid,
                        "sell_client_id": s_cid,
                        "qty": m_qty,
                        "price": f_px,
                        "symbol": sym,
                    }
                )
                rem -= m_qty

                if not dry_run:
                    maker["qty"] -= m_qty
                    print(
                        f"🔄 [MATCH] {sym}: {m_qty} @ {f_px} | buyer={b_id} seller={s_id}",
                        flush=True,
                    )
                    if maker["qty"] <= 0:
                        opp_match.pop(i)
                        continue
                i += 1

            if not dry_run and rem > 0 and new_order.get("tif", "0") not in ("3", "4"):
                queued = dict(new_order)
                queued["qty"] = rem
                book.add_order(queued)
        return matches

    def cancel_order(self, order_id: str) -> Optional[dict]:
        # Removes a specific order from all internal books
        with self._lock:
            return liquidity_manager.cancel_order(order_id)

    def mass_cancel(self, symbol=None, client_id=None) -> list[dict]:
        # Cancels multiple orders based on symbol or client filters
        with self._lock:
            return liquidity_manager.mass_cancel(symbol, client_id)

    def best_bid_ask(self, symbol: str) -> tuple:
        # Returns current BBO for a symbol
        with self._lock:
            b = liquidity_manager.get_book(symbol)
            return b.best_bid(), b.best_ask()


engine = MatchingEngine()
