import traceback
import os
import stripe
import requests
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Shopify and Stripe Keys ---
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")
SHOPIFY_ADMIN_TOKEN = os.getenv("SHOPIFY_ADMIN_TOKEN")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# --- Flask App Setup ---
app = Flask(__name__)

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
                'product_data': {'name': name},
                'unit_amount': unit_amount,
            },
            'quantity': qty,
        })

    if not line_items:
        return jsonify({'error': 'No valid products'}), 400

    try:
        session = stripe.checkout.Session.create(
            line_items=line_items,
            mode='payment',
            billing_address_collection='required',
            shipping_address_collection={
                'allowed_countries': [
                    "AU", "AT", "BE", "BG", "CA", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
                    "DE", "GI", "GR", "HK", "HU", "IE", "IT", "JP", "LV", "LI", "LT", "LU",
                    "MT", "MX", "NL", "NZ", "NO", "PL", "PT", "RO", "SG", "SI", "ES", "SE",
                    "CH", "GB", "US",
                ]
            },
            success_url='https://devsuggests.com/thank-you',
            cancel_url='https://devsuggests.com/cancel',
        )
        print("✅ Stripe session created:", session.url)
        return jsonify({'url': session.url}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Thank You Page (track button) ---
@app.route('/thank-you')
def thank_you():
    return """
    <h1>Thank you for your purchase!</h1>
    <p>You can track your order using the button below:</p>
    <a href='https://track.123track.net' target='_blank'>
        <button>Track My Order</button>
    </a>
    """

# --- Create Shopify Order (w/ shipping)
def create_shopify_order(session_id):
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
        customer_email = session["customer_details"]["email"]
        shipping = session.get("shipping", {})
        address = shipping.get("address", {})

        line_items = []
        for item in session["line_items"]["data"]:
            title = item["description"]
            quantity = item["quantity"]
            price = float(item["price"]["unit_amount"]) / 100
            line_items.append({
                "title": title,
                "quantity": quantity,
                "price": price
            })

        order_data = {
            "order": {
                "email": customer_email,
                "line_items": line_items,
                "financial_status": "paid",
                "shipping_address": {
                    "first_name": shipping.get("name", "").split(' ')[0],
                    "last_name": shipping.get("name", "").split(' ')[-1],
                    "address1": address.get("line1") or address.get("address1"),
                    "address2": address.get("line2") or "",
                    "city": address.get("city"),
                    "province": address.get("state") or address.get("province"),
                    "country": address.get("country"),
                    "zip": address.get("postal_code") or address.get("zip"),
                }
            }
        }

        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
            "Content-Type": "application/json"
        }

        url = f"https://{SHOPIFY_STORE}/admin/api/2023-10/orders.json"
        response = requests.post(url, headers=headers, data=json.dumps(order_data))

        if response.status_code == 201:
            print("✅ Shopify order created.")
        else:
            print("❌ Shopify order failed:", response.status_code, response.text)

    except Exception as e:
        print("❌ Error in create_shopify_order:", str(e))
        traceback.print_exc()

# --- Stripe Webhook
@app.route("/stripe-webhook", methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return 'Invalid payload or signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        print("✅ Checkout session completed:", session["id"])
        create_shopify_order(session["id"])

    return '', 200

# --- Shopify to Stripe Sync
def get_shopify_products():
    url = f"https://{SHOPIFY_STORE}/admin/api/2023-10/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_TOKEN,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("products", [])
    else:
        print(f"❌ Error fetching Shopify products: {response.text}")
        return []

def create_stripe_product(product):
    product_name = product["title"]
    product_desc = product.get("body_html", "")
    price_cents = int(float(product["variants"][0]["price"]) * 100)
    image_url = product.get("image", {}).get("src")

    product_response = stripe.Product.create(
        name=product_name,
        description=product_desc,
        images=[image_url] if image_url else []
    )

    stripe.Price.create(
        unit_amount=price_cents,
        currency="usd",
        product=product_response["id"]
    )

def sync_shopify_to_stripe():
    products = get_shopify_products()
    for product in products:
        create_stripe_product(product)

@app.route('/shopify-webhook', methods=['POST'])
def handle_shopify_product_creation():
    data = request.get_json()
    title = data.get('title')
    price = data.get('variants')[0]['price']
    image_url = data.get('image', {}).get('src')

    product = stripe.Product.create(
        name=title,
        images=[image_url] if image_url else []
    )

    stripe.Price.create(
        unit_amount=int(float(price) * 100),
        currency='usd',
        product=product['id']
    )

    return jsonify({'status': 'success'}), 200

@app.route('/sync-shopify-to-stripe', methods=['POST'])
def manual_sync():
    sync_shopify_to_stripe()
    return "Synced", 200

# --- Run Flask Server ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

