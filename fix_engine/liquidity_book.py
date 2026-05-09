from typing import Optional


class LiquidityBook:
    def __init__(self, symbol: str):
        # Initializes an empty order book for a specific symbol
        self.symbol = symbol
        self.bids = []
        self.asks = []
        self._seq = 0

    def add_order(self, order: dict):
        # Assign a sequence number to ensure FIFO priority at the same price
        order["_seq"] = self._seq
        self._seq += 1

        if str(order["side"]) == "1":
            self.bids.append(order)
            # Sort by Price DESC (highest first), then _seq ASC (oldest first)
            self.bids.sort(key=lambda x: (-float(x["price"]), x["_seq"]))
        else:
            self.asks.append(order)
            # Sort by Price ASC (lowest first), then _seq ASC (oldest first)
            self.asks.sort(key=lambda x: (float(x["price"]), x["_seq"]))

    def remove_order(self, order_id: str) -> Optional[dict]:
        # Removes an order by ID from both sides of the book
        for side in [self.bids, self.asks]:
            for i, o in enumerate(side):
                if o["id"] == order_id:
                    return side.pop(i)
        return None

    def best_bid(self) -> float:
        # Returns the highest bid price currently in the book
        return float(self.bids[0]["price"]) if self.bids else 0.0

    def best_ask(self) -> float:
        # Returns the lowest ask price currently in the book
        return float(self.asks[0]["price"]) if self.asks else 0.0

    def depth(self) -> dict:
        # Returns a full snapshot of resting bids and asks — useful for debugging
        return {
            "bids": [(o["id"], o["price"], o["qty"]) for o in self.bids],
            "asks": [(o["id"], o["price"], o["qty"]) for o in self.asks],
        }


class LiquidityManager:
    def __init__(self):
        # Initializes the manager to track multiple symbol books
        self.books = {}

    def get_book(self, symbol: str) -> LiquidityBook:
        # Returns or creates a liquidity book for a symbol
        if symbol not in self.books:
            self.books[symbol] = LiquidityBook(symbol)
        return self.books[symbol]

    def cancel_order(self, order_id: str) -> Optional[dict]:
        # Scans all books to cancel a specific order
        for book in self.books.values():
            removed = book.remove_order(order_id)
            if removed:
                return removed
        return None

    def mass_cancel(self, symbol=None, client_id=None) -> list[dict]:
        # Performs bulk cancellation based on filters
        canceled = []
        target_books = [self.get_book(symbol)] if symbol else self.books.values()
        for book in target_books:
            for side in [book.bids, book.asks]:
                keep = []
                for o in side:
                    if not client_id or o.get("client_id") == client_id:
                        canceled.append(o)
                    else:
                        keep.append(o)
                side[:] = keep
        return canceled


liquidity_manager = LiquidityManager()
