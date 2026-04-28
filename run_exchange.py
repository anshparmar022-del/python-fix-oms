import quickfix as fix
import time
import threading
from flask import Flask, request, jsonify
from fix_engine.exchange_app import application

# Tiny API to listen for OMS commands
ex_api = Flask(__name__)

@ex_api.route('/manual_fill', methods=['POST'])
def handle_fill_request():
    data = request.json
    # Pass the command to the application logic inside this process
    application.manual_fill_order(
        data.get('clordid'), 
        float(data.get('qty', 0)), 
        float(data.get('price', 0))
    )
    return jsonify({"status": "FIX message sent by Exchange"}), 200

def start_api():
    ex_api.run(port=5001, debug=False, use_reloader=False)

if __name__ == "__main__":
    settings = fix.SessionSettings("config/exchange.cfg")
    acceptor = fix.SocketAcceptor(application, fix.FileStoreFactory(settings), settings, fix.FileLogFactory(settings))
    acceptor.start()
    
    # Start the Command Bridge on 5000
    threading.Thread(target=start_api, daemon=True).start()
    print("🏛️  EXCHANGE LIVE | 🔧 BRIDGE ON PORT 5001")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        acceptor.stop()