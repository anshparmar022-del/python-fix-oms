import quickfix as fix
import quickfix44 as fix44
import time
import uuid
import logging
import queue
import threading
from datetime import datetime

from core.order_manager import manager
from fix_engine.matching_engine import engine
from core.risk_engine import risk_engine
from fix_engine.fix_mapper import FixMapper
from core.models import OrderStateMachine

logger = logging.getLogger("OMS_SYSTEM")


class OMSApp(fix.Application):

    def __init__(self):
        # Initializes the OMS application with session tracking and a lock-free queue bridge.
        super().__init__()
        self.active_session = None
        self.order_tracker = {}
        self.sessions = {}

        self.order_queue = queue.Queue()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def onCreate(self, sessionID):
        # Triggered when a new FIX session is created.
        logger.info("✨ [SYSTEM] Session created: %s", sessionID)

    def onLogon(self, sessionID):
        # Triggered when a client successfully authenticates and logs on.
        self.active_session = sessionID
        client_id = sessionID.getTargetCompID().getValue()
        self.sessions[client_id] = sessionID
        print(
            f"🏛️  [SESSION] Authenticated and Saved: {client_id} ({sessionID})",
            flush=True,
        )

    def onLogout(self, sessionID):
        # Triggered when a client logs out, cleaning up their active session.
        client_id = sessionID.getTargetCompID().getValue()
        self.sessions.pop(client_id, None)
        if self.active_session == sessionID:
            self.active_session = next(iter(self.sessions.values()), None)
        print(f"🔌 [SESSION] Logged OFF: {client_id}", flush=True)

    def toAdmin(self, message, sessionID):
        # Intercepts and logs outgoing administrative FIX messages (Heartbeats, Logons, etc.).
        raw = message.toString().replace("\x01", "|")
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()
        label = "Admin Message"
        if mt == fix.MsgType_Heartbeat:
            return  # Hide heartbeats to keep terminal clean
        elif mt == fix.MsgType_Logon:
            label = "Logon Sent"
        elif mt == fix.MsgType_Logout:
            label = "Logout Sent"
        elif mt == fix.MsgType_TestRequest:
            label = "Test Request"
        print(f"📡 [ADMIN] {label.ljust(15)} | {raw}", flush=True)

    def fromAdmin(self, message, sessionID):
        # Intercepts and logs incoming administrative FIX messages.
        raw = message.toString().replace("\x01", "|")
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()
        label = "Admin Message"
        if mt == fix.MsgType_Heartbeat:
            return  # Hide heartbeats to keep terminal clean
        elif mt == fix.MsgType_Logon:
            label = "Logon Received"
        elif mt == fix.MsgType_Logout:
            label = "Logout Received"
        elif mt == fix.MsgType_TestRequest:
            label = "Test Request ACK"
        print(f"📥 [ADMIN] {label.ljust(15)} | {raw}", flush=True)

    def toApp(self, message, sessionID):
        # Intercepts and logs outgoing application-level FIX messages (Execution Reports).
        raw = message.toString().replace("\x01", "|")
        print(f"📡 [APP]   Outgoing       | {raw}", flush=True)

    def fromApp(self, message, sessionID):
        # Intercepts incoming application messages, copies them safely, and routes them to the worker queue.
        raw = message.toString().replace("\x01", "|")
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        mt = msgType.getValue()
        label = {
            "D": "NewOrderSingle",
            "F": "OrderCancelReq",
            "G": "OrderReplaceReq",
            "q": "MassCancelReq",
            "AN": "PositionRequest",
        }.get(mt, "App Message")
        print(f"📥 [APP]   {label.ljust(15)} | {raw}", flush=True)

        # Deep copy the C++ message string to prevent segfaults when fromApp returns
        msg_copy = fix.Message(message.toString())
        self.order_queue.put((msg_copy, sessionID))

    def _worker_loop(self):
        # Dedicated Single-Writer Thread
        while True:
            try:
                item = self.order_queue.get()
                if item is None:
                    break
                message, sessionID = item
                msgType = fix.MsgType()
                message.getHeader().getField(msgType)
                mt = msgType.getValue()

                if mt == fix.MsgType_NewOrderSingle:
                    self._on_new_order(message, sessionID)
                elif mt == fix.MsgType_OrderCancelRequest:
                    self._on_cancel_request(message, sessionID)
                elif mt == fix.MsgType_OrderCancelReplaceRequest:
                    self._on_replace_request(message, sessionID)
                elif mt == fix.MsgType_OrderMassCancelRequest:
                    self._on_mass_cancel_request(message, sessionID)
                elif mt == "AN":
                    self._on_position_request(message, sessionID)
            except Exception as e:
                logger.exception("_worker_loop failed: %s", e)

    def _on_new_order(self, message, sessionID):
        # Processes NewOrderSingle (35=D) with risk and matching logic
        try:
            data = FixMapper.extract_new_order(message)
            order_id, qty, px, sym, side = (
                data["clord_id"],
                float(data["qty"]),
                float(data["price"]),
                data["symbol"],
                data["side"],
            )
            client_id = self._get_client_id(message, sessionID)
            tif = FixMapper.get_field(message, fix.TimeInForce()) or "0"

            print(
                f"📋 [ORDER] New | id={order_id} sym={sym} side={side} qty={qty} px={px}",
                flush=True,
            )
            if data.get("parties"):
                print(f"👥 [PARTIES] {data['parties']}", flush=True)
            if order_id in self.order_tracker or manager.get_order(order_id):
                self._send_report(
                    order_id,
                    0,
                    0,
                    sym,
                    side,
                    "8",
                    0,
                    text="Duplicate ClOrdID",
                    sessionID=sessionID,
                )
                return
            is_valid, reason = risk_engine.validate_order(sym, qty, px, side, client_id)
            if not is_valid:
                self._send_report(
                    order_id, 0, 0, sym, side, "8", 0, text=reason, sessionID=sessionID
                )
                return

            self.order_tracker[order_id] = {
                "cum_qty": 0.0,
                "total_qty": qty,
                "symbol": sym,
                "side": side,
                "client_id": client_id,
                "session": sessionID,
                "status": "0",
            }
            manager.add_order(
                {
                    "id": order_id,
                    "symbol": sym,
                    "side": side,
                    "qty": qty,
                    "price": px,
                    "client_id": client_id,
                    "leaves_qty": qty,
                }
            )
            self._send_report(order_id, 0, 0, sym, side, "0", 0)

            order_data = {
                "id": order_id,
                "symbol": sym,
                "side": side,
                "qty": qty,
                "price": px,
                "client_id": client_id,
                "timestamp": datetime.now().isoformat(),
                "tif": tif,
            }
            if (
                tif == "4"
                and sum(m["qty"] for m in engine.match_order(order_data, dry_run=True))
                < qty
            ):
                self.order_tracker[order_id]["status"] = "4"
                self._send_report(
                    order_id,
                    0,
                    0,
                    sym,
                    side,
                    "4",
                    0,
                    text="FOK: Insufficient Liquidity",
                    sessionID=sessionID,
                )
                return

            matches = engine.match_order(order_data)
            self._update_bbo(sym)
            for m in matches:
                self._process_fill(m, sym, sessionID)

            if tif == "3":
                tr = self.order_tracker.get(order_id)
                if tr and not OrderStateMachine.is_terminal(tr["status"]):
                    engine.cancel_order(order_id)
                    tr["status"] = "4"
                    self._send_report(
                        order_id,
                        tr["cum_qty"],
                        0,
                        sym,
                        side,
                        "4",
                        0,
                        text="IOC: Remaining Cancelled",
                        sessionID=sessionID,
                    )
                    manager.update_status(order_id, "4")
                    self._update_bbo(sym)
        except Exception as e:
            logger.exception("_on_new_order failed: %s", e)

    def _on_cancel_request(self, message, sessionID):
        # Processes OrderCancelRequest (35=F)
        try:
            data = FixMapper.extract_cancel(message)
            oid, nid, sym = data["orig_clord_id"], data["clord_id"], data["symbol"]
            tr = self.order_tracker.get(oid)
            if tr and OrderStateMachine.is_terminal(tr["status"]):
                self._send_cancel_reject(nid, oid, "Too late to cancel", sessionID)
                return
            if engine.cancel_order(oid):
                if tr:
                    tr["status"] = "4"
                self._send_report(
                    oid,
                    tr["cum_qty"] if tr else 0.0,
                    0,
                    sym,
                    tr["side"] if tr else data["side"],
                    "4",
                    0,
                    sessionID=sessionID,
                )
                manager.update_status(oid, "4")
                self._update_bbo(sym)
            else:
                self._send_cancel_reject(nid, oid, "Unknown Order", sessionID)
        except Exception as e:
            logger.exception("_on_cancel_request failed: %s", e)

    def _on_mass_cancel_request(self, message, sessionID):
        # Processes OrderMassCancelRequest (35=q)
        try:
            cid, sym_f = self._get_client_id(message, sessionID), fix.Symbol()
            sym = FixMapper.get_field(message, sym_f)
            canceled = engine.mass_cancel(symbol=sym, client_id=cid)
            for o in canceled:
                oid, tr = o["id"], self.order_tracker.get(o["id"], {})
                if tr:
                    tr["status"] = "4"
                self._send_report(
                    oid,
                    tr.get("cum_qty", 0.0),
                    0,
                    o["symbol"],
                    o["side"],
                    "4",
                    0,
                    sessionID=sessionID,
                )
                manager.update_status(oid, "4")
            if sym:
                self._update_bbo(sym)
            else:
                [self._update_bbo(s) for s in manager.get_all_symbols()]
            rep = fix.Message()
            rep.getHeader().setField(fix.MsgType("r"))

            # Extract Original ClOrdID if present
            clord_f = fix.ClOrdID()
            clord = FixMapper.get_field(message, clord_f)
            if clord:
                rep.setField(fix.StringField(11, clord))
            else:
                rep.setField(fix.StringField(11, "UNKNOWN"))

            # OrderID (37) is mandatory for MassCancelReport
            rep.setField(fix.StringField(37, "NONE"))

            # MassCancelRequestType (530)
            req_type_f = fix.MassCancelRequestType()
            req_type = (
                message.getField(req_type_f).getString()
                if message.isSetField(req_type_f)
                else "7"
            )

            rep.setField(fix.StringField(530, req_type))
            rep.setField(fix.StringField(531, "1" if sym else "7"))
            rep.setField(fix.IntField(533, len(canceled)))
            rep.setField(fix.StringField(58, f"Canceled {len(canceled)} orders"))
            fix.Session.sendToTarget(rep, sessionID)
        except Exception as e:
            logger.exception("_on_mass_cancel_request failed: %s", e)

    def _on_replace_request(self, message, sessionID):
        # Processes OrderCancelReplaceRequest (35=G)
        try:
            data = FixMapper.extract_replace(message)
            oid, nid, qty, px, sym, side = (
                data["orig_clord_id"],
                data["clord_id"],
                float(data["qty"]),
                float(data["price"]),
                data["symbol"],
                data["side"],
            )
            tr = self.order_tracker.get(oid)
            if tr and OrderStateMachine.is_terminal(tr["status"]):
                self._send_cancel_reject(nid, oid, "Too late to replace", sessionID)
                return
            if engine.cancel_order(oid):
                manager.replace_order(oid, nid, qty, px)
                old = self.order_tracker.pop(oid, {})
                self.order_tracker[nid] = {
                    "cum_qty": 0.0,
                    "total_qty": qty,
                    "symbol": sym,
                    "side": side,
                    "client_id": old.get("client_id"),
                    "session": sessionID,
                    "status": "5",
                }
                od = {
                    "id": nid,
                    "symbol": sym,
                    "side": side,
                    "qty": qty,
                    "price": px,
                    "client_id": old.get("client_id"),
                    "timestamp": datetime.now().isoformat(),
                }
                self._update_bbo(sym)
                self._send_report(nid, 0, px, sym, side, "5", 0, orig_clord_id=oid)
                for m in engine.match_order(od):
                    self._process_fill(m, sym, sessionID)
            else:
                self._send_cancel_reject(nid, oid, "Unknown Order", sessionID)
        except Exception as e:
            logger.exception("_on_replace_request failed: %s", e)

    def _on_position_request(self, message, sessionID):
        # Handles RequestForPositions (35=AN) with individual reports and small delay for test tool stability
        try:
            cid, req_id_f = self._get_client_id(message, sessionID), fix.StringField(
                710
            )
            req_id = (
                req_id_f.getString()
                if message.isSetField(req_id_f) and message.getField(req_id_f)
                else "0"
            )
            positions = manager.get_all_positions(cid)

            # Filter for non-zero positions to keep reports clean and avoid buffer-clogging
            active_positions = [p for p in positions if float(p["net_qty"]) != 0]

            def send_rep(p=None, total=1):
                r = fix44.PositionReport()
                r.setField(fix.PosReqID(req_id))
                r.setField(fix.PosMaintRptID(str(uuid.uuid4())))
                r.setField(fix.Account(cid))
                r.setField(fix.IntField(581, 1))
                r.setField(fix.IntField(728, 0))
                r.setField(fix.ClearingBusinessDate(datetime.now().strftime("%Y%m%d")))
                r.setField(fix.DoubleField(730, float(p["avg_cost"]) if p else 0.0))
                r.setField(fix.DoubleField(734, 0.0))
                r.setField(fix.IntField(731, 1))
                r.setField(fix.IntField(453, 0))
                r.setField(fix.IntField(753, 0))

                if p:
                    r.setField(fix.Symbol(p["symbol"]))
                    r.setField(fix.TotalNumPosReports(total))
                    grp = fix44.PositionReport.NoPositions()
                    grp.setField(fix.PosType(fix.PosType_TRANSACTION_QUANTITY))
                    grp.setField(fix.LongQty(max(float(p["net_qty"]), 0.0)))
                    grp.setField(fix.ShortQty(abs(min(float(p["net_qty"]), 0.0))))
                    r.addGroup(grp)
                    r.setField(fix.Text(f"RealizedPnL={float(p['realized_pnl']):.2f}"))
                else:
                    r.setField(fix.TotalNumPosReports(1))
                    r.setField(fix.IntField(702, 0))
                    r.setField(fix.Text("No active positions found"))

                fix.Session.sendToTarget(r, sessionID)

            if not active_positions:
                send_rep()
            else:
                for p in active_positions:
                    send_rep(p, len(active_positions))
        except Exception as e:
            logger.exception("_on_position_request failed: %s", e)

    def _process_fill(self, m: dict, sym, sessionID):
        # Updates order state and sends reports after a match
        fq, fp = float(m["qty"]), float(m["price"])
        for mid, side, cid in [
            (m["buy_id"], "1", m["buy_client_id"]),
            (m["sell_id"], "2", m["sell_client_id"]),
        ]:
            if mid not in self.order_tracker:
                s = manager.get_order(mid) or {}
                self.order_tracker[mid] = {
                    "cum_qty": float(s.get("filled_qty", 0)),
                    "total_qty": float(s.get("qty", fq)),
                    "symbol": sym,
                    "side": side,
                    "client_id": cid or s.get("client_id", "UNKNOWN"),
                    "session": sessionID,
                }
            self.order_tracker[mid]["cum_qty"] += fq
            cum, total = (
                self.order_tracker[mid]["cum_qty"],
                self.order_tracker[mid]["total_qty"],
            )
            st = "2" if cum >= total else "1"
            self.order_tracker[mid]["status"] = st
            self._send_report(mid, cum, fp, sym, side, st, fq, sessionID=sessionID)
            manager.update_fill(
                mid,
                cum,
                fp,
                st,
                fill_qty=fq,
                symbol=sym,
                side=side,
                client_id=self.order_tracker[mid].get("client_id"),
            )
            bid, ask = engine.best_bid_ask(sym)
            manager.update_market_data(sym, fq, fp, bid, ask)
            print(
                f"✅ [FILL] {'FILLED' if st == '2' else 'PARTIAL'} | id={mid} qty={fq}",
                flush=True,
            )

    def _get_client_id(self, message, sessionID) -> str:
        # Prefers Account (Tag 1) for tracking, falls back to SenderCompID
        acc = fix.Account()
        if message.isSetField(acc):
            message.getField(acc)
            return acc.getValue()
        return sessionID.getTargetCompID().getValue()

    def _update_bbo(self, symbol):
        bid, ask = engine.best_bid_ask(symbol)
        manager.update_bbo(symbol, bid, ask)

    def _send_report(
        self,
        clord_id,
        cum,
        px,
        sym,
        side,
        status,
        last,
        orig_clord_id=None,
        text=None,
        sessionID=None,
    ):
        # Builds and sends ExecutionReport (35=8)
        try:
            tr = self.order_tracker.get(str(clord_id), {})
            target = (
                sessionID
                or tr.get("session")
                or self.sessions.get(tr.get("client_id"))
                or self.active_session
            )
            if not target:
                return
            er = fix44.ExecutionReport()
            er.setField(fix.ClOrdID(str(clord_id))), er.setField(
                fix.OrderID(str(clord_id))
            ), er.setField(fix.ExecID(str(int(time.time() * 1000)))), er.setField(
                fix.Symbol(str(sym))
            ), er.setField(
                fix.Side(str(side))
            )
            er.setField(fix.OrderQty(float(tr.get("total_qty", cum)))), er.setField(
                fix.CumQty(float(cum))
            ), er.setField(fix.AvgPx(float(px))), er.setField(
                fix.LastQty(float(last))
            ), er.setField(
                fix.LastPx(float(px))
            ), er.setField(
                fix.LeavesQty(max(0.0, float(tr.get("total_qty", cum)) - float(cum)))
            )
            if tr.get("client_id"):
                er.setField(fix.StringField(1, str(tr.get("client_id"))))
            er.setField(
                fix.ExecType(
                    {"0": "0", "1": "F", "2": "F", "4": "4", "5": "5", "8": "8"}.get(
                        str(status), str(status)
                    )
                )
            )
            er.setField(
                fix.OrdStatus(
                    {"0": "0", "1": "1", "2": "2", "4": "4", "5": "0", "8": "8"}.get(
                        str(status), str(status)
                    )
                )
            )
            if orig_clord_id:
                er.setField(fix.OrigClOrdID(str(orig_clord_id)))
            if text:
                er.setField(fix.Text(str(text)))
            fix.Session.sendToTarget(er, target)
            label = {
                "0": "ACK (NEW)",
                "1": "PARTIAL FILL",
                "2": "FULL FILL",
                "4": "CANCELLED",
                "5": "REPLACED",
                "8": "REJECTED",
            }.get(str(status), status)
            logger.info("📡 [REPORT] %s | ClOrdID=%s", label, clord_id)
        except Exception as e:
            logger.exception("_send_report failed: %s", e)

    def _send_cancel_reject(self, clord_id, orig_clord_id, reason, sessionID=None):
        # Builds and sends OrderCancelReject (35=9)
        try:
            tr = self.order_tracker.get(str(orig_clord_id), {})
            target = (
                sessionID
                or tr.get("session")
                or self.sessions.get(tr.get("client_id"))
                or self.active_session
            )
            if not target:
                return
            rj = fix44.OrderCancelReject()
            rj.setField(fix.OrderID(str(orig_clord_id))), rj.setField(
                fix.ClOrdID(str(clord_id))
            ), rj.setField(fix.OrigClOrdID(str(orig_clord_id))), rj.setField(
                fix.OrdStatus(fix.OrdStatus_REJECTED)
            ), rj.setField(
                fix.CxlRejResponseTo(fix.CxlRejResponseTo_ORDER_CANCEL_REQUEST)
            ), rj.setField(
                fix.Text(str(reason))
            ), rj.setField(
                fix.TransactTime()
            )
            fix.Session.sendToTarget(rj, target)
        except Exception as e:
            logger.exception("_send_cancel_reject failed: %s", e)

    def shutdown(self):
        # Gracefully drains the queue and stops the worker thread
        self.order_queue.put(None)
        if self.worker.is_alive():
            self.worker.join(timeout=5.0)


application = OMSApp()
