from datetime import datetime

class PositionService:
    @staticmethod
    def calculate_new_position(current_pos, side, qty, price):
        """
        Calculates the new position state (net_qty, avg_cost, realized_pnl) based on a trade.
        
        current_pos: dict with 'net_qty', 'avg_cost', 'realized_pnl' or None
        side: "1" for Buy, "2" for Sell
        qty: trade quantity (float)
        price: trade price (float)
        """
        cur_qty, cur_cost, cur_pnl = (
            (current_pos["net_qty"], current_pos["avg_cost"], current_pos["realized_pnl"])
            if current_pos
            else (0.0, 0.0, 0.0)
        )
        
        trade_qty = qty if str(side) == "1" else -qty
        new_qty = cur_qty + trade_qty
        new_cost, new_pnl = cur_cost, cur_pnl
        
        # If adding to the same direction (long getting longer or short getting shorter)
        if cur_qty * trade_qty >= 0:
            if new_qty != 0:
                new_cost = (cur_qty * cur_cost + trade_qty * price) / new_qty
        else:
            # Closing or reversing position
            closed_qty = min(abs(cur_qty), abs(trade_qty))
            # P&L = closed_qty * (exit_price - entry_price) for long, (entry_price - exit_price) for short
            new_pnl += closed_qty * (
                price - cur_cost if cur_qty > 0 else cur_cost - price
            )
            
            if new_qty != 0:
                # If reversed, new cost is the trade price
                # If reduced, new cost remains the old average cost
                new_cost = price if abs(trade_qty) > abs(cur_qty) else cur_cost
            else:
                new_cost = 0.0
                
        return {
            "net_qty": new_qty,
            "avg_cost": new_cost,
            "realized_pnl": new_pnl,
            "updated_at": datetime.now().isoformat()
        }
