import requests
import os
from datetime import datetime, timedelta, timezone

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]
MARKETPLACE_ID = "ATVPDKIKX0ER"
LOG_FILE = "requested_orders.txt"

def get_access_token():
    r = requests.post("https://api.amazon.com/auth/o2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    r.raise_for_status()
    return r.json()["access_token"]

def get_all_orders(token):
    start = (datetime.now(timezone.utc) - timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_orders = []
    next_token = None

    while True:
        params = {
            "MarketplaceIds": MARKETPLACE_ID,
            "CreatedAfter": start,
        }
        if next_token:
            params = {"MarketplaceIds": MARKETPLACE_ID, "NextToken": next_token}

        r = requests.get(
            "https://sellingpartnerapi-na.amazon.com/orders/v0/orders",
            headers={"x-amz-access-token": token},
            params=params
        )
        
        print(f"Status code: {r.status_code}")
        print(f"Response: {r.text[:500]}")
        
        r.raise_for_status()
        payload = r.json().get("payload", {})
        all_orders.extend(payload.get("Orders", []))

        next_token = payload.get("NextToken")
        if not next_token:
            break

    print(f"Total orders found: {len(all_orders)}")
    return all_orders

def get_delivery_date(token, order_id):
    r = requests.get(
        f"https://sellingpartnerapi-na.amazon.com/orders/v0/orders/{order_id}",
        headers={"x-amz-access-token": token},
        params={"MarketplaceIds": MARKETPLACE_ID}
    )
    payload = r.json().get("payload", {})
    date_str = payload.get("ActualDeliveryDate") or payload.get("LastUpdateDate")
    if not date_str:
        return None
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))

def already_requested(order_id):
    try:
        with open(LOG_FILE, "r") as f:
            return order_id in f.read()
    except FileNotFoundError:
        return False

def log_requested(order_id):
    with open(LOG_FILE, "a") as f:
        f.write(order_id + "\n")

def request_review(token, order_id):
    r = requests.post(
        f"https://sellingpartnerapi-na.amazon.com/solicitations/v1/orders/{order_id}/solicitations/productReview",
        headers={"x-amz-access-token": token},
        params={"marketplaceIds": MARKETPLACE_ID}
    )
    return r.status_code

def main():
    token = get_access_token()
    orders = get_all_orders(token)
    now = datetime.now(timezone.utc)

    success = 0
    skipped_log = 0
    skipped_window = 0
    failed = 0

    for order in orders:
        order_id = order["AmazonOrderId"]

        if already_requested(order_id):
            skipped_log += 1
            continue

        delivery_date = get_delivery_date(token, order_id)
        if not delivery_date:
            print(f"SKIP (no date): {order_id}")
            continue

        days_since = (now - delivery_date).days

        if days_since < 5 or days_since > 30:
            skipped_window += 1
            continue

        status = request_review(token, order_id)
        if status == 201:
            print(f"SUCCESS: {order_id} ({days_since} days since delivery)")
            log_requested(order_id)
            success += 1
        else:
            print(f"FAILED ({status}): {order_id}")
            failed += 1

    print(f"\nDone — Sent: {success} | Already logged: {skipped_log} | Outside window: {skipped_window} | Failed: {failed}")

if __name__ == "__main__":
    main()
