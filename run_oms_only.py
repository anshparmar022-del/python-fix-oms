import threading
import redis
import json
import re
import quickfix as fix
import os
import time
from core.order_manager import manager
from fix_engine.oms_app import send_raw_fix

# Always run relative to this file's directory — works from any location
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from api.server import app
from fix_engine.oms_app import application as oms_app

def shutdown(initiator):
    print("\n🛰️  OMS Shutdown Initiated — sending Logout (35=5)...", flush=True)
    sessionID = fix.SessionID("FIX.4.4", "OMS_NEW", "EXCHANGE_NEW")
    session = fix.Session.lookupSession(sessionID)

    if session and session.isLoggedOn():
        session.logout("User Exit")
        timeout, waited = 5, 0
        while not getattr(oms_app, 'logged_out', False) and waited < timeout:
            time.sleep(0.1)
            waited += 0.1
        if getattr(oms_app, 'logged_out', False):
            print("✅ Logout handshake complete.", flush=True)
        else:
            print("⚠️  No logout reply within timeout — forcing stop.", flush=True)
    else:
        print("ℹ️  Session not active, stopping directly.", flush=True)

    initiator.stop()
    print("🛰️  OMS process stopped.", flush=True)

def market_connector_worker():
    """Listens for validated orders and sends them to the Exchange."""
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    print("📡 [Background] Market Connector Active.")
    while True:
        try:
            _, raw_fix = r.blpop("market_ready_queue")
            send_raw_fix(raw_fix)
            clordid_match = re.search(r"11=([^|]+)", raw_fix)
            if clordid_match:
                manager.update_status(clordid_match.group(1), "0")
        except Exception as e:
            print(f"❌ Connector Error: {e}")

def kill_switch_worker():
    """Listens for risk rejections and updates the DB."""
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    print("🛡️ [Background] Kill Switch Active.")
    while True:
        try:
            _, payload = r.blpop("oms_kill_switch")
            data = json.loads(payload)
            manager.update_status(data['id'], "RISK_REJECTED")
            print(f"🚨 RISK REJECTED: {data['id']}")
        except Exception as e:
            print(f"❌ Kill Switch Error: {e}")

if __name__ == "__main__":
    settings = fix.SessionSettings("config/oms.cfg")
    initiator = fix.SocketInitiator(
        oms_app,
        fix.FileStoreFactory(settings),
        settings,
        fix.FileLogFactory(settings)
    )

    oms_app.initiator = initiator
    oms_app.logged_out = False

    # Start ALL background workers
    threading.Thread(target=initiator.start, daemon=True).start()
    #threading.Thread(target=market_connector_worker, daemon=True).start()
    #threading.Thread(target=kill_switch_worker, daemon=True).start()

    # Start Flask API
    flask_thread = threading.Thread(
        target=lambda: app.run(debug=False, port=5000, use_reloader=False),
        daemon=True
    )
    flask_thread.start()

    print("🌐 OMS API running on http://127.0.0.1:5000", flush=True)
    print("   Press Ctrl+C to shutdown cleanly.", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(initiator)