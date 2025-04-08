import requests
import json
from flask import Flask, request, jsonify, redirect
import stripe

# 🛍️ Shopify Store Details
SHOPIFY_STORE = "DevSuggests.com"
SHOPIFY_API_KEY = "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"

# 💳 Stripe Secret Key
STRIPE_SECRET_KEY = "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"
stripe.api_key = STRIPE_SECRET_KEY

# --- Flask App Setup ---
app = Flask(__name__)

@app.route('/create-stripe-checkout-session', methods=['POST'])
def create_checkout_session():
    # Use form data instead of JSON
    product_name = request.form.get('product_name')
    product_price = request.form.get('product_price')

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': product_name,
                    },
                    'unit_amount': int(float(product_price) * 100),  # convert dollars to cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://devsuggests.com/pages/success',
            cancel_url='https://devsuggests.com/pages/cancel',
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# --- Shopify to Stripe Sync (Optional) ---
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
    product_desc = product["body_html"] or ""
    price_cents = int(float(product["variants"][0]["price"]) * 100)

    product_data = {
        "name": product_name,
        "description": product_desc,
    }

    product_response = requests.post(
        "https://api.stripe.com/v1/products",
        data=product_data,
        auth=(STRIPE_SECRET_KEY, "")
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
            auth=(STRIPE_SECRET_KEY, "")
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
                auth=(STRIPE_SECRET_KEY, "")
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
        return

def sync_shopify_to_stripe():
    products = get_shopify_products()
    if not products:
        print("No products found.")
        return

    for product in products:
        create_stripe_product(product)
        
@app.route('/')
def home():
    return "Flask app is running!"

# --- Run the Server ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)

