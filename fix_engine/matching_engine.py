import threading

class MatchingEngine:
    def __init__(self):
        self.bids = []  # Buy orders
        self.asks = []  # Sell orders
        self._lock = threading.Lock()

    def match_order(self, new_order):
        with self._lock:
            matches = []
            symbol = new_order['symbol']
            side = new_order['side']
            price = new_order['price']

            target_book = self.asks if side == '1' else self.bids

            i = 0
            while i < len(target_book) and new_order['qty'] > 0:
                maker_order = target_book[i]

                price_match = (side == '1' and price >= maker_order['price']) or \
                              (side == '2' and price <= maker_order['price'])

                if maker_order['symbol'] == symbol and price_match:
                    match_qty = min(new_order['qty'], maker_order['qty'])

                    matches.append({
                        'buy_id':  new_order['id'] if side == '1' else maker_order['id'],
                        'sell_id': maker_order['id'] if side == '1' else new_order['id'],
                        'qty':   match_qty,
                        'price': maker_order['price']
                    })

                    new_order['qty']    -= match_qty
                    maker_order['qty']  -= match_qty

                    if maker_order['qty'] == 0:
                        target_book.pop(i)
                        continue
                i += 1

            if new_order['qty'] > 0:
                if side == '1':
                    self.bids.append(new_order)
                    self.bids.sort(key=lambda x: x['price'], reverse=True)
                else:
                    self.asks.append(new_order)
                    self.asks.sort(key=lambda x: x['price'])
            return matches

    def cancel_order(self, order_id):
        with self._lock:
            for i, order in enumerate(self.bids):
                if order['id'] == order_id:
                    return self.bids.pop(i)
            for i, order in enumerate(self.asks):
                if order['id'] == order_id:
                    return self.asks.pop(i)
            return None

    def get_book_snapshot(self):
        """Return a thread-safe copy of the order book."""
        with self._lock:
            return {
                "bids": list(self.bids),
                "asks": list(self.asks)
            }

engine = MatchingEngine()