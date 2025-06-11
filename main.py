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
SHOPIFY_STORE = os.getenv("SHOPIFY_STORE")  # e.g., "yourstore.myshopify.com"
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

    # --- Stripe Checkout Session ---
:contentReference[oaicite:1]{index=1}
def create_checkout_session():
    
    try:
        session = stripe.checkout.Session.create(
            # let Stripe decide eligible payment methods dynamically
            line_items=line_items,
            mode='payment',
            billing_address_collection='required',
            shipping_address_collection={
                'allowed_countries': [
                    # All ISO country codes supported by Stripe (note: include 'SD' as of Jan 2025) :contentReference[oaicite:3]{index=3}
                    'AF','AL','DZ','AS','AD','AO','AG','AR','AM','AU','AT','AZ','BS','BH',
                    'BD','BB','BY','BE','BZ','BJ','BT','BO','BA','BW','BR','BN','BG','BF',
                    'BI','KH','CM','CA','CV','KY','CF','TD','CL','CN','CO','KM','CG','CR',
                    'CI','HR','CU','CY','CZ','DK','DJ','DM','DO','EC','EG','SV','GQ','ER',
                    'EE','ET','FJ','FI','FR','GA','GM','GE','DE','GH','GI','GR','GL','GD',
                    'GT','GG','GN','GW','GY','HT','HN','HK','HU','IS','IN','ID','IE','IL',
                    'IT','JM','JP','JE','JO','KZ','KE','KI','KW','KG','LA','LV','LB','LS',
                    'LR','LI','LT','LU','MO','MK','MG','MW','MY','MV','ML','MT','MH','MR',
                    'MU','MX','FM','MD','MC','MN','ME','MA','MZ','MM','NA','NR','NP','NL',
                    'NZ','NI','NE','NG','NO','OM','PK','PW','PA','PG','PY','PE','PH','PL',
                    'PT','QA','RO','RU','RW','KN','LC','VC','WS','SM','ST','SA','SN','RS',
                    'SC','SL','SG','SK','SI','SB','ZA','KR','ES','LK','LC','SR','SZ','SE',
                    'CH','TW','TJ','TZ','TH','TG','TO','TT','TN','TR','TV','UG','UA','AE',
                    'GB','US','UY','UZ','VU','VE','VN','YE','ZM','ZW','SD'
                ]
            },
            success_url='https://DevSuggests.com',
            cancel_url='https://DevSuggests.com/cancel',
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Create Shopify Order ---
def create_shopify_order(session_id):
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
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
        response = requests.post(url, headers=headers, data=json.dumps(order_data))

        if response.status_code == 201:
            print("✅ Shopify order created.")
        else:
            print("❌ Shopify order failed:", response.status_code, response.text)

    except Exception as e:
        print("❌ Error in create_shopify_order:", str(e))
        traceback.print_exc()

# --- Stripe Webhook ---
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

# --- Shopify to Stripe Sync ---
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

# --- Run Flask Server ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

