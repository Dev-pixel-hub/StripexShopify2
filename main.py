import traceback
import os
import stripe
import requests
import json
from flask import Flask, request, redirect, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Shopify and Stripe Keys ---
SHOPIFY_STORE = "DevSuggests.com"
SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # Only use from .env

# --- Flask App Setup ---
app = Flask(__name__)

# Home route
@app.route('/')
def home():
    return "Flask app is running!"

@app.route('/ping')
def ping():
    return "OK", 200

# --- Stripe Checkout Session ---
@app.route('/create-stripe-checkout-session', methods=['POST'])
def create_checkout_session():
    product_names = request.form.getlist('product_name[]')
    product_prices = request.form.getlist('product_price[]')
    quantities = request.form.getlist('quantity[]')

    if not product_names or not product_prices:
        return jsonify({'error': 'Missing product name or price'}), 400

    # Create line items
    line_items = []
    for name, price, quantity in zip(product_names, product_prices, quantities):
        try:
            unit_amount = int(float(price) * 100)
            qty = int(quantity)
            if qty <= 0:
                continue
        except ValueError:
            return jsonify({'error': 'Invalid price or quantity format'}), 400

        line_items.append({
            'price_data': {
                'currency': 'usd',
                'product_data': {
                    'name': name,
                },
                'unit_amount': unit_amount,
            },
            'quantity': qty,
        })

    if not line_items:
        return jsonify({'error': 'No valid products'}), 400

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            success_url='https://DevSuggest.com/succsess',
            cancel_url='https://DevSuggests.com/cancel',
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Shopify to Stripe Sync ---
def get_shopify_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-10/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print("✅ Fetched products from Shopify.")
        return response.json().get("products", [])
    else:
        print(f"❌ Error fetching Shopify products: {response.text}")
        return []

def create_stripe_product(product):
    product_name = product["title"]
    product_desc = product.get("body_html", "")
    price_cents = int(float(product["variants"][0]["price"]) * 100)

    product_data = {
        "name": product_name,
        "description": product_desc,
    }

    product_response = requests.post(
        "https://api.stripe.com/v1/products",
        data=product_data,
        auth=(stripe.api_key, "")
    )

    if product_response.status_code == 200:
        stripe_product = product_response.json()
        print(f"✅ Created product '{product_name}' in Stripe.")

        price_data = {
            "unit_amount": price_cents,
            "currency": "usd",
            "product": stripe_product["id"]
        }

        price_response = requests.post(
            "https://api.stripe.com/v1/prices",
            data=price_data,
            auth=(stripe.api_key, "")
        )

        if price_response.status_code == 200:
            stripe_price = price_response.json()

            checkout_data = {
                "line_items[0][price]": stripe_price["id"],
                "line_items[0][quantity]": 1,
                "mode": "payment",
                "success_url": "https://devsuggests.com/pages/success",
                "cancel_url": "https://devsuggests.com/pages/cancel"
            }

            session_response = requests.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=checkout_data,
                auth=(stripe.api_key, "")
            )

            if session_response.status_code == 200:
                session = session_response.json()
                print(f"🛒 Checkout Link: {session['url']}")
            else:
                print("⚠️ Failed to create checkout session.")
        else:
            print("⚠️ Failed to create price in Stripe.")
    else:
        print("❌ Failed to create Stripe product.")
        print(f"🔎 Stripe Response: {product_response.status_code} {product_response.text}")

def sync_shopify_to_stripe():
    products = get_shopify_products()
    if not products:
        print("No products found.")
        return

    for product in products:
        create_stripe_product(product)

# --- Run the Server ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
