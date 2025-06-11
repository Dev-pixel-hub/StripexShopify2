import os
import stripe
import requests
import json
import traceback
from flask import Flask, request, redirect, jsonify
from dotenv import load_dotenv

# --- Load .env variables ---
load_dotenv()

# --- Environment Variables ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")  # e.g. devsuggests.myshopify.com
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")

# --- Flask App ---
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Flask app running on Render!"

@app.route("/ping")
def ping():
    return "OK", 200

# --- Stripe Checkout Session ---
@app.route("/create-stripe-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        product_names = request.form.getlist("product_name[]")
        product_prices = request.form.getlist("product_price[]")
        quantities = request.form.getlist("quantity[]")

        if not product_names or not product_prices:
            return jsonify({"error": "Missing product name or price"}), 400

        line_items = []
        for name, price, quantity in zip(product_names, product_prices, quantities):
            unit_amount = int(float(price) * 100)
            line_items.append({
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": name},
                    "unit_amount": unit_amount,
                },
                "quantity": int(quantity),
            })

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=line_items,
            success_url="https://devsuggests.com/success",
            cancel_url="https://devsuggests.com/cancel",
        )
        return redirect(session.url, code=303)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Shopify Order Creation ---
def create_shopify_order(session_data):
    try:
        session = stripe.checkout.Session.retrieve(session_data["id"], expand=["line_items"])
        line_items = []

        for item in session["line_items"]["data"]:
            line_items.append({
                "title": item["description"],
                "quantity": item["quantity"],
                "price": float(item["price"]["unit_amount"]) / 100
            })

        shopify_order = {
            "order": {
                "email": session["customer_details"]["email"],
                "line_items": line_items,
                "financial_status": "paid"
            }
        }

        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
            "Content-Type": "application/json"
        }

        url = f"https://{SHOPIFY_STORE}/admin/api/2023-10/orders.json"
        response = requests.post(url, headers=headers, json=shopify_order)

        if response.status_code == 201:
            print("✅ Shopify order created.")
        else:
            print("❌ Shopify order failed:", response.status_code, response.text)

    except Exception as e:
        print("❌ Error in create_shopify_order:", str(e))
        traceback.print_exc()

# --- Stripe Webhook ---
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print("✅ Stripe checkout completed:", session["id"])
        create_shopify_order(session)

    return "", 200

# --- Run Server ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
