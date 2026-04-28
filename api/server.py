from flask import Flask, request, jsonify
from core.order_manager import manager
import uuid
import requests
import redis
import json

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

app = Flask(__name__)

# ---------- helpers ----------

def _require_fields(data, *fields):
    missing = [f for f in fields if data.get(f) is None]
    return missing

# ---------- orders ----------

@app.route('/order', methods=['POST'])
def create_order():
    data = request.json or {}
    missing = _require_fields(data, 'symbol', 'side', 'qty', 'price')
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    if data['side'] not in ('1', '2'):
        return jsonify({"error": "side must be '1' (buy) or '2' (sell)"}), 400
    if float(data['qty']) <= 0 or float(data['price']) <= 0:
        return jsonify({"error": "qty and price must be positive"}), 400

    order = {
        'id':     str(uuid.uuid4()),
        'symbol': str(data['symbol']).upper(),
        'side':   str(data['side']),
        'qty':    float(data['qty']),
        'price':  float(data['price']),
        'status': 'PENDING_RISK'  # Track that it's waiting for validation
    }
    
    # 1. Save to local DB first
    manager.add_order(order)

    # 2. Convert to raw FIX string to send to Validator
    # We use a helper to build the FIX string (8=FIX.4.4|9=... etc)
    from fix_engine.oms_app import build_fix_string # You may need to create this helper
    # Added 49=OMS_NEW and 56=EXCHANGE_NEW so the Validator recognizes the session
    raw_fix = f"8=FIX.4.4|35=D|49=OMS_NEW|56=EXCHANGE_NEW|11={order['id']}|55={order['symbol']}|38={order['qty']}|44={order['price']}|54={order['side']}|10=000|"
    # 3. PUSH to Risk Gateway
    r.rpush("oms_outbound_queue", raw_fix)

    return jsonify({"status": "Sent to Risk Gateway", "id": order['id']}), 201


@app.route('/orders', methods=['GET'])
def get_orders():
    status = request.args.get('status')
    symbol = request.args.get('symbol')
    orders = manager.get_all_orders()
    if status:
        orders = [o for o in orders if o['status'] == status.upper()]
    if symbol:
        orders = [o for o in orders if o['symbol'] == symbol.upper()]
    return jsonify(orders)


@app.route('/order/<order_id>', methods=['GET'])
def get_order(order_id):
    order = manager.get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(order)


@app.route('/order/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    order = manager.get_order(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order['status'] in ('FILLED', 'CANCELED'):
        return jsonify({"error": f"Cannot cancel order with status '{order['status']}'"}), 400
    from fix_engine.oms_app import send_cancel
    send_cancel(order_id)
    return jsonify({"message": "Cancel request sent", "id": order_id}), 202


@app.route('/order/cancel', methods=['POST'])
def cancel_specific_order():
    data = request.json or {}
    clordid = data.get('clordid')
    if not clordid:
        return jsonify({"error": "clordid is required"}), 400
    order = manager.get_order(clordid)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    if order['status'] in ('FILLED', 'CANCELED'):
        return jsonify({"error": f"Cannot cancel order with status '{order['status']}'"}), 400
    from fix_engine.oms_app import send_cancel
    send_cancel(clordid)
    return jsonify({"status": "Cancel request sent", "target": clordid}), 202


@app.route('/order/replace', methods=['POST'])
def replace_order():
    data = request.json or {}
    missing = _require_fields(data, 'orig_clordid', 'symbol', 'side', 'qty', 'price')
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    orig_id = data['orig_clordid']
    order = manager.get_order(orig_id)
    if not order:
        return jsonify({"error": "Original order not found"}), 404
    if order['status'] in ('FILLED', 'CANCELED'):
        return jsonify({"error": f"Cannot replace order with status '{order['status']}'"}), 400

    new_details = {
        'id':     str(uuid.uuid4()),
        'symbol': str(data['symbol']).upper(),
        'side':   str(data['side']),
        'qty':    float(data['qty']),
        'price':  float(data['price'])
    }
    from fix_engine.oms_app import send_replace
    send_replace(orig_id, new_details)
    return jsonify({"status": "Replace request sent", "orig_id": orig_id, "new_id": new_details['id']}), 202


# ---------- book ----------

@app.route('/book', methods=['GET'])
def get_book():
    from fix_engine.matching_engine import engine
    return jsonify(engine.get_book_snapshot())


# ---------- exchange admin (proxies to exchange process on :5001) ----------

# ---------- exchange admin (Direct internal call) ----------

@app.route('/exchange/simulate_fill', methods=['POST'])
def simulate_fill():
    data = request.json or {}
    import requests
    
    # Forward the "Command" to the Exchange process
    try:
        resp = requests.post(
            "http://127.0.0.1:5001/manual_fill", 
            json=data, 
            timeout=2
        )
        return jsonify({
            "status": "Success", 
            "message": "FIX Report triggered", 
            "exchange_ack": resp.json()
        }), 200
    except Exception as e:
        return jsonify({"error": f"Exchange Bridge (5001) is down: {e}"}), 503

if __name__ == "__main__":
    app.run(port=5000)