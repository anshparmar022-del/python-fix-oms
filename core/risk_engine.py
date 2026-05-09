import logging

logger = logging.getLogger("OMS_SYSTEM")

# Default institutional risk limits applied to all clients
DEFAULT_LIMITS = {
    "MAX_QTY": 10000,
    "MAX_POSITION_QTY": 500000,
    "MAX_NOTIONAL": 10000000,
    "MIN_PRICE": 0.0001,
    "MAX_PRICE": 999999.0,
    "PRICE_DEVIATION_PCT": 0.10,
}

# Override limits per client — add any SenderCompID here to apply tighter or looser limits
CLIENT_LIMITS = {
    # Example: tighter limits for CLIENT2
    # "CLIENT2": {
    #     "MAX_QTY": 500,
    #     "MAX_NOTIONAL": 1_000_000,
    # }
}


class RiskEngine:
    def validate_order(
        self, symbol: str, qty: float, price: float, side=None, client_id=None
    ) -> tuple[bool, str]:
        # Merge default limits with any per-client overrides
        limits = {**DEFAULT_LIMITS, **CLIENT_LIMITS.get(client_id or "", {})}
        q, p = float(qty), float(price)

        if q <= 0 or q > limits["MAX_QTY"]:
            return False, "Invalid quantity"
        if p < limits["MIN_PRICE"] or p > limits["MAX_PRICE"]:
            return False, "Invalid price"
        if q * p > limits["MAX_NOTIONAL"]:
            return False, "Notional limit exceeded"

        try:
            from fix_engine.matching_engine import engine

            b, a = engine.best_bid_ask(symbol)
            ref = (
                (b + a) / 2 if b > 0 and a > 0 else b if b > 0 else a if a > 0 else None
            )
            if ref and abs(p - ref) / ref > limits["PRICE_DEVIATION_PCT"]:
                return False, "Fat Finger: Price deviates >10% from market"
        except Exception as e:
            logger.warning("Fat-finger check skipped: %s", e)

        if side and client_id:
            from core.order_manager import manager

            pos = (
                manager.get_position(client_id, symbol)
                if hasattr(manager, "get_position")
                else None
            )
            curr = float(pos["net_qty"]) if pos else 0.0
            if abs(curr + (q if str(side) == "1" else -q)) > limits["MAX_POSITION_QTY"]:
                return False, "Position limit exceeded"

        return True, "PASS"


risk_engine = RiskEngine()
