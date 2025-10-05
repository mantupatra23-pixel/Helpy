# app.py - Helpy backend (cloud-ready)
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import requests
import uuid
import logging

# ---------- Config ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")        # use service_role key on server only
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
ZAPIER_WEBHOOK = os.getenv("ZAPIER_WEBHOOK")
STRIPE_SECRET = os.getenv("STRIPE_SECRET")      # optional

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.INFO)

# ---------- Helpers ----------
def supabase_insert(table, payload):
    """Insert row and return inserted data (or raise)"""
    res = supabase.table(table).insert(payload).execute()
    if res.error:
        app.logger.error("Supabase insert error: %s", res.error)
        raise Exception(res.error)
    return res.data

def supabase_select(table, filters=None, single=False, order=None):
    q = supabase.table(table).select("*")
    if filters:
        for k, v in filters.items():
            q = q.eq(k, v)
    if order:
        q = q.order(order)
    res = q.execute()
    if res.error:
        app.logger.error("Supabase select error: %s", res.error)
        raise Exception(res.error)
    if single:
        return res.data[0] if res.data else None
    return res.data

def supabase_update(table, where: dict, payload: dict):
    q = supabase.table(table)
    for k, v in where.items():
        q = q.eq(k, v)
    res = q.update(payload).execute()
    if res.error:
        app.logger.error("Supabase update error: %s", res.error)
        raise Exception(res.error)
    return res.data

# ---------- Health ----------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Helpy API running"}), 200

# ---------- Users ----------
@app.route("/users", methods=["POST"])
def create_user():
    data = request.json or {}
    # basic validation
    if not data.get("email") or not data.get("name"):
        return jsonify({"error":"name and email required"}), 400
    try:
        out = supabase_insert("users", data)
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/users", methods=["GET"])
def list_users():
    try:
        rows = supabase_select("users")
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Products ----------
@app.route("/products", methods=["POST"])
def add_product():
    data = request.json or {}
    required = ["shop_id","name","price"]
    if not all(k in data for k in required):
        return jsonify({"error": f"required fields: {required}"}), 400
    try:
        out = supabase_insert("products", data)
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/products", methods=["GET"])
def get_products():
    shop_id = request.args.get("shop_id")
    q = supabase.table("products").select("*")
    if shop_id:
        q = q.eq("shop_id", shop_id)
    res = q.execute()
    if res.error:
        return jsonify({"error": str(res.error)}), 500
    return jsonify(res.data)

# ---------- Orders ----------
@app.route("/orders", methods=["POST"])
def create_order():
    data = request.json or {}
    required = ["customer_id","total_amount"]
    if not all(k in data for k in required):
        return jsonify({"error": f"required fields: {required}"}), 400
    # ensure tracking id
    if not data.get("tracking_id"):
        data["tracking_id"] = str(uuid.uuid4())[:12]
    try:
        out = supabase_insert("orders", data)
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/orders/<tracking_id>", methods=["GET"])
def get_order_by_tracking(tracking_id):
    try:
        rows = supabase_select("orders", filters={"tracking_id": tracking_id})
        if not rows:
            return jsonify({"error":"order not found"}), 404
        return jsonify(rows[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/orders/id/<order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    data = request.json or {}
    status = data.get("status")
    if not status:
        return jsonify({"error":"status required"}), 400
    try:
        out = supabase_update("orders", {"id": order_id}, {"status": status})
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Messages (chat history) ----------
@app.route("/messages", methods=["POST"])
def post_message():
    data = request.json or {}
    required = ["order_id","sender","content"]
    if not all(k in data for k in required):
        return jsonify({"error": f"required: {required}"}), 400
    try:
        out = supabase_insert("messages", data)
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/messages/order/<order_id>", methods=["GET"])
def fetch_messages_for_order(order_id):
    try:
        q = supabase.table("messages").select("*").eq("order_id", order_id).order("created_at", {"ascending": True})
        res = q.execute()
        if res.error:
            raise Exception(res.error)
        return jsonify(res.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Tickets ----------
@app.route("/tickets", methods=["POST"])
def create_ticket():
    data = request.json or {}
    if not data.get("issue") or not data.get("order_id"):
        return jsonify({"error":"order_id and issue required"}), 400
    try:
        out = supabase_insert("tickets", data)
        # optional: fire Zapier webhook
        if ZAPIER_WEBHOOK:
            try:
                requests.post(ZAPIER_WEBHOOK, json={
                    "ticket": out,
                }, timeout=5)
            except Exception as e:
                app.logger.warning("Zapier webhook failed: %s", e)
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/tickets", methods=["GET"])
def list_tickets():
    try:
        rows = supabase_select("tickets")
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Delivery Boys ----------
@app.route("/delivery_boys", methods=["POST"])
def create_delivery_boy():
    data = request.json or {}
    if not data.get("name") or not data.get("phone"):
        return jsonify({"error":"name & phone required"}), 400
    try:
        out = supabase_insert("delivery_boys", data)
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/delivery_boys", methods=["GET"])
def get_delivery_boys():
    try:
        rows = supabase_select("delivery_boys")
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Order Assignments ----------
@app.route("/assign_order", methods=["POST"])
def assign_order():
    data = request.json or {}
    if not data.get("order_id") or not data.get("delivery_boy_id"):
        return jsonify({"error":"order_id and delivery_boy_id required"}), 400
    try:
        out = supabase_insert("order_assignments", data)
        # set delivery boy status to busy
        try:
            supabase_update("delivery_boys", {"id": data.get("delivery_boy_id")}, {"status":"busy"})
        except Exception:
            pass
        return jsonify(out), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/assignments/order/<order_id>", methods=["GET"])
def get_assignment_for_order(order_id):
    try:
        rows = supabase_select("order_assignments", filters={"order_id": order_id})
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Admin Settings (control pricing / tokens /plan) ----------
# Note: create a simple settings table in Supabase: settings (key text primary key, value jsonb)
@app.route("/admin/settings", methods=["GET"])
def get_settings():
    try:
        rows = supabase_select("settings")
        # return as key->value map
        out = {r["key"]: r["value"] for r in rows} if rows else {}
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/settings", methods=["POST"])
def set_setting():
    data = request.json or {}
    key = data.get("key")
    value = data.get("value")
    if not key:
        return jsonify({"error":"key required"}), 400
    # upsert into settings
    try:
        # delete old then insert (supabase upsert also possible)
        supabase.table("settings").delete().eq("key", key).execute()
        res = supabase.table("settings").insert({"key": key, "value": value}).execute()
        if res.error:
            raise Exception(res.error)
        return jsonify(res.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- Payment webhook placeholder (Stripe) ----------
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    # Implement signature verification using STRIPE_SECRET if you use Stripe
    payload = request.get_json()
    # handle events here (payment.succeeded etc.)
    app.logger.info("Stripe webhook event received")
    return jsonify({"received": True})

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
