import io
import pytest
import pandas as pd


def create_inventory_dataset_bytes(rows=40) -> bytes:
    """Create dataset with SKU, Demand, Current Stock, Lead Time, and Unit Cost."""
    records = []
    skus = ["SKU_ALPHA", "SKU_BETA", "SKU_GAMMA", "SKU_DELTA"]
    for i in range(rows):
        sku = skus[i % len(skus)]
        # Make ALPHA low stock, BETA normal, GAMMA overstocked
        if sku == "SKU_ALPHA":
            stock = 5
            demand = 20
        elif sku == "SKU_BETA":
            stock = 150
            demand = 10
        elif sku == "SKU_GAMMA":
            stock = 800
            demand = 5
        else:
            stock = 50
            demand = 12

        records.append({
            "product_id": sku,
            "demand": demand,
            "stock_on_hand": stock,
            "lead_time": 5,
            "unit_cost": 15.50,
        })
    df = pd.DataFrame(records)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def inventory_dataset(client, owner_user):
    """Fixture uploading inventory-ready dataset."""
    headers = owner_user["headers"]
    csv_bytes = create_inventory_dataset_bytes()
    upload_resp = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory_data.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    assert upload_resp.status_code == 201
    return upload_resp.json()["id"]


def test_inventory_kpis_calculation(client, owner_user, inventory_dataset):
    """Verify safety stock, reorder point, and risk classification calculations."""
    headers = owner_user["headers"]
    dataset_id = inventory_dataset

    resp = client.get(f"/api/v1/inventory/kpis?dataset_id={dataset_id}&service_level=0.95", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["dataset_id"] == dataset_id
    assert "summary" in data
    assert data["summary"]["total_skus"] >= 4
    assert data["summary"]["total_inventory_value"] > 0
    assert len(data["items"]) >= 4

    # Verify SKU_ALPHA is classified as CRITICAL or REORDER_NOW due to low stock
    alpha_item = next(i for i in data["items"] if i["sku"] == "SKU_ALPHA")
    assert alpha_item["status"] in ["CRITICAL", "REORDER_NOW"]
    assert alpha_item["recommended_reorder_qty"] > 0
    assert alpha_item["reorder_point"] > alpha_item["current_stock"]

    # Verify SKU_GAMMA is classified as OVERSTOCK
    gamma_item = next(i for i in data["items"] if i["sku"] == "SKU_GAMMA")
    assert gamma_item["status"] == "OVERSTOCK"
    assert gamma_item["overstock_capital"] > 0


def test_copilot_query_stockout_and_reorder(client, owner_user, inventory_dataset):
    """Verify Copilot answers stockout questions grounded in real dataset SKUs."""
    headers = owner_user["headers"]

    resp = client.post(
        "/api/v1/copilot/query",
        json={"prompt": "Which products are at critical risk of stockout?"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "SKU_ALPHA" in data["answer"]
    assert len(data["grounded_sources"]) >= 1


def test_copilot_query_overstock(client, owner_user, inventory_dataset):
    """Verify Copilot detects overstocked capital."""
    headers = owner_user["headers"]

    resp = client.post(
        "/api/v1/copilot/query",
        json={"prompt": "How much working capital is tied up in overstocked goods?"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "SKU_GAMMA" in data["answer"] or "$" in data["answer"]


def test_copilot_prompts_endpoint(client, owner_user):
    """Verify Copilot starter prompts endpoint."""
    headers = owner_user["headers"]

    resp = client.get("/api/v1/copilot/prompts", headers=headers)
    assert resp.status_code == 200
    prompts = resp.json()
    assert len(prompts) >= 3


def test_inventory_cross_tenant_isolation(client, owner_user, second_owner, inventory_dataset):
    """Verify Tenant B cannot access Tenant A's inventory data."""
    headers_b = second_owner["headers"]
    dataset_id = inventory_dataset

    resp = client.get(f"/api/v1/inventory/kpis?dataset_id={dataset_id}", headers=headers_b)
    assert resp.status_code == 404
