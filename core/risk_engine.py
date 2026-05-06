import logging
logger = logging.getLogger("OMS_SYSTEM")

class RiskEngine:
    def __init__(self):
        # Configuration for pre-trade risk limits
        self.limits = {
            "MAX_QTY": 10000,
            "MAX_POSITION_QTY": 500000,
            "MAX_NOTIONAL": 10000000,
            "MIN_PRICE": 0.0001,
            "MAX_PRICE": 999999.0,
            "PRICE_DEVIATION_PCT": 0.10,
            "ALLOWED_SYMBOLS": {"AAPL", "MSFT", "GOOG", "RELIANCE", "NVDA", "FILLTEST", "PARTIAL", "TSLA"}
        }
    
    def validate_order(self, symbol: str, qty: float, price: float, side=None, client_id=None) -> tuple[bool, str]:
        # Validates order parameters against institutional risk limits
        q, p = float(qty), float(price)
        if symbol not in self.limits["ALLOWED_SYMBOLS"]: return False, "Symbol not allowed"
        if q <= 0 or q > self.limits["MAX_QTY"]: return False, "Invalid quantity"
        if p < self.limits["MIN_PRICE"] or p > self.limits["MAX_PRICE"]: return False, "Invalid price"
        if q * p > self.limits["MAX_NOTIONAL"]: return False, "Notional limit exceeded"

        try:
            from fix_engine.matching_engine import engine
            b, a = engine.best_bid_ask(symbol)
            ref = (b+a)/2 if b>0 and a>0 else b if b>0 else a if a>0 else None
            if ref and abs(p - ref)/ref > self.limits["PRICE_DEVIATION_PCT"]:
                return False, f"Fat Finger: Price deviates >10% from market"
        except: pass

        if side and client_id:
            from core.order_manager import manager
            pos = manager.get_position(client_id, symbol) if hasattr(manager, 'get_position') else None
            curr = float(pos["net_qty"]) if pos else 0.0
            if abs(curr + (q if str(side)=="1" else -q)) > self.limits["MAX_POSITION_QTY"]:
                return False, "Position limit exceeded"
        return True, "PASS"

risk_engine = RiskEngine()
