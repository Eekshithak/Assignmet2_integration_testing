import time
import uuid
import requests
import pytest

# Base URL for Kong (adjust if testing directly on microservice ports)
GATEWAY_URL = "http://localhost:8000"


# -----------------------------------------------------------------------------
# Test Case 1: Validate User Creation and Retrieval
# -----------------------------------------------------------------------------
def test_user_creation_and_retrieval():
    
    user_data = {
        "firstName": "Test",
        "lastName": "User",
        "emails": [f"test_{uuid.uuid4().hex[:6]}@example.com"],
        "phoneNumber": "1234567890",
        "deliveryAddress": {
            "street": "123 Main St",
            "city": "TestCity",
            "state": "TC",
            "postalCode": "11111",
            "country": "Testland"
        }
    }
    # Use trailing slash as per Kong config
    post_response = requests.post(f"{GATEWAY_URL}/users/", json=user_data)
    assert post_response.status_code == 201, f"Expected 201, got {post_response.status_code}"
    created_user = post_response.json()
    user_id = created_user.get("userId")
    assert user_id, "User ID not returned in the response"

    get_response = requests.get(f"{GATEWAY_URL}/users/{user_id}")
    assert get_response.status_code == 200, f"Expected 200, got {get_response.status_code}"
    retrieved_user = get_response.json()

    assert retrieved_user.get("firstName") == user_data["firstName"]
    assert retrieved_user.get("lastName") == user_data["lastName"]
    assert retrieved_user.get("emails") == user_data["emails"]
    assert retrieved_user.get("deliveryAddress") == user_data["deliveryAddress"]


# -----------------------------------------------------------------------------
# Test Case 2: Validate Order Creation with Existing User
# -----------------------------------------------------------------------------
def test_order_creation_with_existing_user():
    
    user_data = {
        "firstName": "Order",
        "lastName": "Tester",
        "emails": [f"ordertester_{uuid.uuid4().hex[:6]}@example.com"],
        "phoneNumber": "7397643667",
        "deliveryAddress": {
            "street": "456 Order St",
            "city": "OrderCity",
            "state": "OC",
            "postalCode": "22222",
            "country": "Orderland"
        }
    }
    user_resp = requests.post(f"{GATEWAY_URL}/users/", json=user_data)
    assert user_resp.status_code == 201, "User creation failed"
    created_user = user_resp.json()
    user_id = created_user.get("userId")
    assert user_id, "User ID not returned"

    order_data = {
        "userId": user_id,
        "items": [
            {"itemId": "prod001", "quantity": 2, "price": 19.99}
        ],
        "userEmails": user_data["emails"],
        "deliveryAddress": user_data["deliveryAddress"],
        "orderStatus": "under process"
    }
    order_resp = requests.post(f"{GATEWAY_URL}/orders", json=order_data)
    assert order_resp.status_code == 201, "Order creation failed"
    created_order = order_resp.json()

    assert created_order.get("userId") == user_id, "Order does not reference the correct user"


# -----------------------------------------------------------------------------
# Test Case 3: Validate Event-Driven User Update Propagation
# -----------------------------------------------------------------------------
def test_event_driven_user_update_propagation():
    

    user_data = {
        "firstName": "Sync",
        "lastName": "Tester",
        "emails": [f"sync_{uuid.uuid4().hex[:6]}@example.com"],
        "phoneNumber": "7845865096",
        "deliveryAddress": {
            "street": "789 Sync Ave",
            "city": "SyncCity",
            "state": "SC",
            "postalCode": "33333",
            "country": "Syncland"
        }
    }
    user_resp = requests.post(f"{GATEWAY_URL}/users/", json=user_data)
    assert user_resp.status_code == 201, "User creation failed"
    user_id = user_resp.json().get("userId")
    assert user_id, "User ID not returned"

    order_data = {
        "userId": user_id,
        "items": [
            {"itemId": "prod002", "quantity": 1, "price": 49.99}
        ],
        "userEmails": user_data["emails"],
        "deliveryAddress": user_data["deliveryAddress"],
        "orderStatus": "under process"
    }
    order_resp = requests.post(f"{GATEWAY_URL}/orders", json=order_data)
    assert order_resp.status_code == 201, "Order creation failed"

    updated_data = {
        "emails": [f"updated_{uuid.uuid4().hex[:6]}@example.com"],
        "deliveryAddress": {
            "street": "999 Updated Blvd",
            "city": "UpdateCity",
            "state": "UP",
            "postalCode": "44444",
            "country": "Updatedland"
        }
    }
    put_resp = requests.put(f"{GATEWAY_URL}/users/{user_id}", json=updated_data)
    assert put_resp.status_code == 200, "User update failed"

    time.sleep(5)

    orders_resp = requests.get(f"{GATEWAY_URL}/orders?status=under%20process")
    assert orders_resp.status_code == 200, "Failed to retrieve orders"
    orders = orders_resp.json()

    relevant_orders = [order for order in orders if order.get("userId") == user_id]
    assert relevant_orders, "No orders found for the updated user"

    updated_order = relevant_orders[0]
    assert updated_order.get("userEmails") == updated_data["emails"], "Order emails not updated"
    assert updated_order.get("deliveryAddress") == updated_data["deliveryAddress"], "Order address not updated"

    # -----------------------------------------------------------------------------
# Test Case 4: Validate API Gateway Routing (Strangler Pattern)
# -----------------------------------------------------------------------------
def test_api_gateway_routing():
    """
    Objective: Ensure the API Gateway routes requests between User Service v1 and v2
    according to the configured traffic split (strangler pattern).
    Steps:
    1. Send multiple POST requests to /users/ via the API Gateway.
    2. Verify that each request returns HTTP 201.
    3. Optionally, if responses include version information, check that responses come from both v1 and v2.
    
    Note: If your service does not return a version indicator, this test will simply validate that the gateway routes successfully.
    """
    versions = []
    for _ in range(10):
        user_data = {
            "firstName": "Routing",
            "lastName": "Tester",
            "emails": [f"routing_{uuid.uuid4().hex[:6]}@example.com"],
            "deliveryAddress": {
                "street": "321 Route Rd",
                "city": "RouteCity",
                "state": "RC",
                "postalCode": "22222",
                "country": "Routeland"
            }
        }
        response = requests.post(f"{GATEWAY_URL}/users/", json=user_data)
        assert response.status_code == 201, f"Expected 201, got {response.status_code}"
        data = response.json()
        # If your response includes a version field (e.g., "version": "v1" or "v2"), capture it.
        version = data.get("version", "unknown")
        versions.append(version)
    
    
    if "unknown" not in versions:
        assert len(set(versions)) > 1, "API Gateway did not route to both versions"



