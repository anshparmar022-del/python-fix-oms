import quickfix as fix
import quickfix44 as fix44
import time
from fix_engine.matching_engine import engine

GLOBAL_SESSION_ID = fix.SessionID("FIX.4.4", "EXCHANGE_NEW", "OMS_NEW")

class ExchangeApp(fix.Application):
    def __init__(self):
        super().__init__()
        self.active_session = None  # Add this to store the session
        self.order_tracker = {}

    def onCreate(self, sessionID): pass
    def onLogon(self, sessionID):
        self.active_session = sessionID 
        print(f"🏛️  Exchange Logged ON and Session Saved: {sessionID}", flush=True)
    def onLogout(self, sessionID):
        print(f"🏛️  Exchange Logged OFF", flush=True)
        # Signal that the logout handshake is complete (35=5 received from OMS)
        self.logged_out = True

    def toAdmin(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == "5":
            print(f"📤 EXCHANGE SENDING LOGOUT (35=5): {raw}", flush=True)
        else:
            print(f"📡 EXCHANGE ADMIN SENDING: {raw}", flush=True)

    def fromAdmin(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == "5":
            print(f"📥 EXCHANGE RECEIVED LOGOUT (35=5): {raw}", flush=True)
        else:
            print(f"📥 EXCHANGE ADMIN RECEIVING: {raw}", flush=True)

    def toApp(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        print(f"\n📡 EXCHANGE SENDING RAW: {raw}")

    def fromApp(self, message, sessionID):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        m_val = msgType.getValue()
        if m_val == "D": self.on_new_order(message)
        elif m_val == "F": self.on_cancel_request(message)
        elif m_val == "G": self.on_replace_request(message) # Add this line

    def on_replace_request(self, message):
        orig_id = fix.OrigClOrdID(); message.getField(orig_id)
        new_id = fix.ClOrdID(); message.getField(new_id)
        qty = fix.OrderQty(); message.getField(qty)
        px = fix.Price(); message.getField(px)
    
    # 1. Remove from matching engine RAM
        removed_order = engine.cancel_order(orig_id.getValue())
    
        if removed_order:
            new_id_val = new_id.getValue()
        
        # 2. Update Database (CRITICAL: This is what we were missing)
        # This ensures the manual fill logic can find the new ID in the DB
            from core.order_manager import manager
            manager.replace_order(orig_id.getValue(), new_id_val, qty.getValue(), px.getValue())
        
        # 3. Update Tracker RAM
            self.order_tracker[new_id_val] = {'cum': 0, 'total': qty.getValue()}

            new_order = {
                'id': new_id_val,
                'symbol': removed_order['symbol'],
                'side': removed_order['side'],
                'qty': qty.getValue(),
                'price': px.getValue()
            }
            engine.match_order(new_order)
        
        # 4. Send Report with Status "5" (REPLACED)
            self.send_report(
                clord_id=new_id_val, 
                cum_qty=0, 
                price=px.getValue(), 
                symbol=new_order['symbol'], 
                side=new_order['side'], 
                status="5", 
                last_qty=0, 
                orig_clord_id=orig_id.getValue()
            )
            print(f"🏛️ Exchange REPLACED: {orig_id.getValue()} -> {new_id_val}")
    # Update this method signature to accept orig_clord_id
    def on_new_order(self, message):
        clid = fix.ClOrdID(); message.getField(clid)
        sym = fix.Symbol(); message.getField(sym)
        side = fix.Side(); message.getField(side)
        qty = fix.OrderQty(); message.getField(qty)
        px = fix.Price(); message.getField(px)

        order_id = clid.getValue()
        orig_qty = qty.getValue()
        self.order_tracker[order_id] = {'cum_qty': 0, 'total_qty': orig_qty}

        self.send_report(order_id, 0, 0, sym.getValue(), side.getValue(), "0", 0)

        new_order = {'id': order_id, 'symbol': sym.getValue(), 'side': side.getValue(), 'qty': orig_qty, 'price': px.getValue()}
        matches = engine.match_order(new_order)
        
        for m in matches:
            for target_id in [m['buy_id'], m['sell_id']]:
                self.order_tracker[target_id]['cum_qty'] += m['qty']
                cum = self.order_tracker[target_id]['cum_qty']
                total = self.order_tracker[target_id]['total_qty']
                status = "2" if cum == total else "1"
                report_side = "1" if target_id == m['buy_id'] else "2"
                self.send_report(target_id, cum, m['price'], sym.getValue(), report_side, status, m['qty'])

    def on_cancel_request(self, message):
        orig_id = fix.OrigClOrdID(); message.getField(orig_id)
        sym = fix.Symbol(); message.getField(sym)
        side = fix.Side(); message.getField(side)
        
        removed = engine.cancel_order(orig_id.getValue())
        if removed:
            print(f"🚫 Removing {orig_id.getValue()} from Book")
            self.send_report(orig_id.getValue(), 0, 0, sym.getValue(), side.getValue(), "4", 0)
    
    def manual_fill_order(self, clord_id, fill_qty, fill_price):
        """Manually fills an order and ensures the tracker is initialized from the DB if needed."""
        from core.order_manager import manager
        
        # 1. Always fetch the latest ground truth from the Database
        order = manager.get_order(clord_id)
        if not order:
            print(f"❌ Manual Fill Error: Order {clord_id} not found.")
            return

        # 2. THE FIX: Initialize or update the tracker using Database values
        # This prevents the KeyError if the matching engine used different keys
        if clord_id not in self.order_tracker or not isinstance(self.order_tracker[clord_id], dict):
            self.order_tracker[clord_id] = {}

        tracker = self.order_tracker[clord_id]
        
        # Pull current state from tracker OR fallback to Database values
        current_cum = tracker.get('cum', float(order.get('filled_qty', 0)))
        total_qty = tracker.get('total', float(order.get('qty', 0)))

        # 3. Perform the math
        new_cum = current_cum + float(fill_qty)
        tracker['cum'] = new_cum
        tracker['total'] = total_qty
        
        # 4. Determine FIX Status (1=Partial, 2=Full)
        status = "2" if new_cum >= total_qty else "1"

        # 5. Send the official FIX message
        self.send_report(
            clord_id=clord_id,
            cum_qty=new_cum,
            price=fill_price,
            symbol=order['symbol'],
            side=order['side'],
            status=status,
            last_qty=fill_qty
        )

    # CRITICAL: Ensure this is indented exactly like 'manual_fill_order'
    def send_report(self, clord_id, cum_qty, price, symbol, side, status, last_qty, **kwargs):
        er = fix44.ExecutionReport()
        er.setField(fix.OrderID(str(clord_id))) 
        er.setField(fix.ExecID(str(int(time.time()*1000))))
        er.setField(fix.Symbol(str(symbol)))
        er.setField(fix.Side(str(side)))
        er.setField(fix.CumQty(float(cum_qty)))
        er.setField(fix.AvgPx(float(price)))
        er.setField(fix.LastQty(float(last_qty)))
        er.setField(fix.LastPx(float(price)))
        er.setField(fix.OrdStatus(str(status)))
        er.setField(fix.ExecType(str(status)))
        
        # Calculate LeavesQty
        total = self.order_tracker.get(clord_id, {}).get('total', cum_qty)
        er.setField(fix.LeavesQty(max(0, total - cum_qty)))

        target = fix.SessionID("FIX.4.4", "EXCHANGE_NEW", "OMS_NEW")
        fix.Session.sendToTarget(er, target)
        #print(f"✅ Sent FIX Execution Report for {clord_id} (Status: {status})")
application = ExchangeApp()