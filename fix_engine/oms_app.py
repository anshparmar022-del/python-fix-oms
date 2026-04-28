import quickfix as fix
import quickfix44 as fix44
import time
from core.order_manager import manager

class OMSApp(fix.Application):
    def __init__(self):
        super().__init__()
        self.initiator = None  # To be set in run_oms_only.py

    def onCreate(self, sessionID): pass

    def onLogon(self, sessionID): 
        print(f"🛰️  OMS Logged ON: {sessionID}", flush=True)

    def onLogout(self, sessionID):
        print(f"🛰️  OMS SESSION TERMINATED: {sessionID}", flush=True)
        # Signal that the logout handshake is complete (35=5 received from exchange)
        self.logged_out = True
        # KILL SWITCH: Stop the engine so it can't try to reconnect
        if self.initiator:
            self.initiator.stop()

    def toAdmin(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == "5":
            print(f"📤 OMS SENDING LOGOUT (35=5): {raw}", flush=True)
        else:
            print(f"📡 OMS ADMIN SENDING: {raw}", flush=True)

    def fromAdmin(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == "5":
            print(f"📥 OMS RECEIVED LOGOUT (35=5): {raw}", flush=True)
        else:
            print(f"📥 OMS ADMIN RECEIVING: {raw}", flush=True)

    def toApp(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        print(f"📡 OMS SENDING RAW: {raw}", flush=True)

    def fromApp(self, message, sessionID):
        raw = message.toString().replace('\x01', '|')
        print(f"📥 OMS RECEIVING RAW: {raw}", flush=True)
        try:
            msgType = fix.MsgType()
            message.getHeader().getField(msgType)
            if msgType.getValue() == "8":
                self.on_execution_report(message)
        except Exception as e:
            print(f"❌ OMS Receiver Error: {str(e)}")

    def on_execution_report(self, message):
        try:
            import quickfix as fix
            from core.order_manager import manager

            # Tag 37 is the UUID we use as our primary key
            order_id = self.get_field(message, fix.OrderID())
            if not order_id:
                order_id = self.get_field(message, fix.ClOrdID())

            ord_status = self.get_field(message, fix.OrdStatus())
            cum_qty = float(self.get_field(message, fix.CumQty()) or 0)
            avg_px = float(self.get_field(message, fix.AvgPx()) or 0)
            last_qty = float(self.get_field(message, fix.LastQty()) or 0)

            # Record the update in the database
            if last_qty > 0 or ord_status in ("1", "2"):
                manager.update_fill(order_id, cum_qty, avg_px, ord_status)
                #print(f"✅ DB UPDATED FILL: {order_id} (Status: {ord_status})")
            else:
                manager.update_status(order_id, ord_status)
                #print(f"✅ DB UPDATED STATUS: {order_id} -> {ord_status}")

        except Exception as e:
            print(f"❌ Error in on_execution_report: {e}")

    def get_field(self, message, field_obj):
        """Helper to safely extract fields without throwing errors."""
        try:
            message.getField(field_obj)
            return field_obj.getString()
        except:
            return None

application = OMSApp()

def send_order(order):
    message = fix44.NewOrderSingle()
    message.setField(fix.ClOrdID(str(order['id'])))
    message.setField(fix.Symbol(str(order['symbol'])))
    message.setField(fix.Side(str(order['side'])))
    message.setField(fix.OrderQty(float(order['qty'])))
    message.setField(fix.Price(float(order['price'])))
    message.setField(fix.OrdType(fix.OrdType_LIMIT))
    message.setField(fix.TransactTime())
    fix.Session.sendToTarget(message, fix.SessionID("FIX.4.4", "OMS_NEW", "EXCHANGE_NEW"))

def send_cancel(order_id):
    order = manager.get_order(order_id)
    if not order:
        print(f"❌ Cancel failed: Order '{order_id}' not found in DB.", flush=True)
        return

    message = fix44.OrderCancelRequest()
    message.setField(fix.OrigClOrdID(str(order_id)))
    message.setField(fix.ClOrdID("CAN-" + str(int(time.time()))))
    message.setField(fix.Symbol(str(order['symbol'])))
    message.setField(fix.Side(str(order['side'])))
    message.setField(fix.TransactTime())
    fix.Session.sendToTarget(message, fix.SessionID("FIX.4.4", "OMS_NEW", "EXCHANGE_NEW"))

def send_replace(orig_id, new_order):
    message = fix44.OrderCancelReplaceRequest()
    message.setField(fix.OrigClOrdID(str(orig_id)))
    message.setField(fix.ClOrdID(str(new_order['id'])))
    message.setField(fix.Symbol(str(new_order['symbol'])))
    message.setField(fix.Side(str(new_order['side'])))
    message.setField(fix.OrderQty(float(new_order['qty'])))
    message.setField(fix.Price(float(new_order['price'])))
    message.setField(fix.OrdType(fix.OrdType_LIMIT))
    message.setField(fix.TransactTime())
    fix.Session.sendToTarget(message, fix.SessionID("FIX.4.4", "OMS_NEW", "EXCHANGE_NEW"))

def send_raw_fix(raw_string):
    """
    Parses the validated string and builds a proper QuickFIX object 
    to ensure headers (8, 9, 35) are in the correct order.
    """
    import quickfix as fix
    import quickfix44 as fix44
    import re

    # 1. Extract values from the validated string using Regex
    def get_tag(tag, string):
        match = re.search(f"{tag}=([^|]+)", string)
        return match.group(1) if match else None

    # 2. Create a proper NewOrderSingle object (35=D)
    message = fix44.NewOrderSingle()
    
    # 3. Manually map the validated data into the object
    # QuickFIX will handle the Tag 8, 9, and 10 (Checksum) automatically!
    message.setField(fix.ClOrdID(get_tag(11, raw_string)))
    message.setField(fix.Symbol(get_tag(55, raw_string)))
    message.setField(fix.Side(get_tag(54, raw_string)))
    message.setField(fix.OrderQty(float(get_tag(38, raw_string))))
    message.setField(fix.Price(float(get_tag(44, raw_string))))
    message.setField(fix.OrdType(fix.OrdType_LIMIT))
    message.setField(fix.TransactTime())

    # 4. Send to the Exchange
    target = fix.SessionID("FIX.4.4", "OMS_NEW", "EXCHANGE_NEW")
    try:
        fix.Session.sendToTarget(message, target)
        print(f"📡 FIX Engine: Properly formatted message sent to Exchange.")
    except Exception as e:
        print(f"❌ FIX Error: {e}")

def build_fix_string(order):
    """
    Converts the order dictionary into a raw FIX string for the Validator.
    Note: We use pipes '|' which the Validator's parse_fix_message expects.
    """
    import time
    t_time = time.strftime("%Y%m%d-%H:%M:%S")
    # Tag 11=ID, 55=Symbol, 38=Qty, 44=Price, 54=Side, 60=Time
    raw = f"8=FIX.4.4|35=D|11={order['id']}|55={order['symbol']}|38={order['qty']}|44={order['price']}|54={order['side']}|60={t_time}|10=000|"
    return raw