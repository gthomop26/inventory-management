"""
Tests for restock order endpoints.
"""


class TestRestockOrders:
    def test_create_order_uses_server_prices_and_max_lead_time(self, client):
        inv = {i["sku"]: i for i in client.get("/api/inventory").json()}
        a, b = inv["FLT-405"], inv["MTR-304"]  # lead times 5 and 30
        before = len(client.get("/api/restock-orders").json())

        res = client.post("/api/restock-orders", json={"items": [
            {"sku": "FLT-405", "quantity": 10}, {"sku": "MTR-304", "quantity": 2}]})
        assert res.status_code == 201
        order = res.json()
        assert order["total_value"] == round(10 * a["unit_cost"] + 2 * b["unit_cost"], 2)
        assert order["lead_time_days"] == 30
        assert order["status"] == "Processing"
        assert order["expected_delivery"] > order["order_date"]

        listed = client.get("/api/restock-orders").json()
        assert len(listed) == before + 1
        assert listed[0]["id"] == order["id"]

    def test_unknown_sku_returns_404(self, client):
        res = client.post("/api/restock-orders", json={"items": [{"sku": "NOPE-1", "quantity": 1}]})
        assert res.status_code == 404

    def test_invalid_quantity_returns_400(self, client):
        for q in (0, -5):
            res = client.post("/api/restock-orders", json={"items": [{"sku": "FLT-405", "quantity": q}]})
            assert res.status_code == 400

    def test_empty_items_returns_400(self, client):
        assert client.post("/api/restock-orders", json={"items": []}).status_code == 400

    def test_demand_skus_exist_in_inventory(self, client):
        skus = {i["sku"] for i in client.get("/api/inventory").json()}
        assert {d["item_sku"] for d in client.get("/api/demand").json()} <= skus
