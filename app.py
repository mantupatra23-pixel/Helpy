from flask import Flask, request, jsonify
import openai, os, requests
from datetime import datetime

app = Flask(__name__)

# Environment variables (Render/Termux में set करो)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ZAPIER_URL = os.getenv("ZAPIER_WEBHOOK")

openai.api_key = OPENAI_KEY


@app.route("/")
def home():
    return "✅ Helpy Backend is running!"


# --- Chat Endpoint ---
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")

    # Simple order ID check
    if any(char.isdigit() for char in user_message):
        order_id = ''.join(filter(str.isdigit, user_message))
        order_data = check_order(order_id)
        if order_data:
            return jsonify({
                "reply": f"आपका ऑर्डर {order_id} अभी {order_data['status']} है।",
                "location": order_data.get("location", None)
            })

    # Else send to GPT
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"You are a helpful Hindi customer support agent."},
            {"role":"user","content": user_message}
        ]
    )
    reply = response['choices'][0]['message']['content']
    return jsonify({"reply": reply})


# --- Escalation Endpoint ---
@app.route("/escalate", methods=["POST"])
def escalate():
    data = request.json
    issue = data.get("issue", "No details")
    customer = data.get("customer", "Unknown")

    if ZAPIER_URL:
        requests.post(ZAPIER_URL, json={
            "customer": customer,
            "issue": issue,
            "time": str(datetime.now())
        })
        return jsonify({"status": "Ticket escalated to support!"})
    return jsonify({"error": "Zapier webhook not set"}), 500


# --- Analytics (Dummy) ---
@app.route("/analytics")
def analytics():
    return jsonify({
        "total_chats": 125,
        "positive": 90,
        "negative": 15,
        "neutral": 20,
        "tickets_escalated": 5
    })


# --- Helper ---
def check_order(order_id):
    # Dummy order lookup (replace with Supabase query)
    if order_id == "12345":
        return {"status": "in transit", "location": "Delhi"}
    return None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
