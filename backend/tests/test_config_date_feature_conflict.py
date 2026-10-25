import io
import pytest
import pandas as pd
from app.services.dataset_service import validate_dataset_configuration, suggest_default_configuration
from app.models.dataset import DatasetConfiguration


def create_grocery_style_csv() -> bytes:
    """Create CSV mimicking Grocery Inventory with dates, stock, and expiry."""
    df = pd.DataFrame({
        "Product_ID": [f"PROD_{i}" for i in range(40)],
        "Product_Name": [f"Item_{i}" for i in range(40)],
        "Date_Received": pd.date_range("2026-01-01", periods=40, freq="D").strftime("%Y-%m-%d"),
        "Last_Order_Date": pd.date_range("2026-01-05", periods=40, freq="D").strftime("%Y-%m-%d"),
        "Expiration_Date": pd.date_range("2026-06-01", periods=40, freq="D").strftime("%Y-%m-%d"),
        "Stock_Quantity": [50 + (i * 3) % 40 for i in range(40)],
        "Unit_Price": [12.5 + (i % 5) for i in range(40)],
        "Warehouse_Location": [f"WH_{(i % 3) + 1}" for i in range(40)],
        "Category": ["Dairy" if i % 2 == 0 else "Bakery" for i in range(40)],
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def test_suggest_default_configuration_excludes_target_and_date_from_entities(client, owner_user):
    """Verify suggest_default_configuration excludes date and target from features and entities."""
    csv_bytes = create_grocery_style_csv()
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory.csv", csv_bytes, "text/csv")},
        data={"name": "Grocery Test"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    sugg_res = client.get(
        f"/api/v1/datasets/{dataset_id}/suggested-config",
        headers=owner_user["headers"],
    )
    assert sugg_res.status_code == 200
    sugg = sugg_res.json()

    target = sugg["target_column"]
    date_col = sugg["date_column"]
    features = sugg["feature_columns"]
    entities = sugg["entity_columns"]

    assert target not in features
    if date_col:
        assert date_col not in features
        assert date_col not in entities
    assert target not in entities


def test_save_config_rejects_date_column_in_feature_columns(client, owner_user):
    """Verify backend returns 400 when date_column is also included in feature_columns."""
    csv_bytes = create_grocery_style_csv()
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory_date_test.csv", csv_bytes, "text/csv")},
        data={"name": "Date Conflict Test"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Attempt to save configuration with Expiration_Date in feature_columns
    payload = {
        "task_type": "forecasting",
        "target_column": "Stock_Quantity",
        "date_column": "Expiration_Date",
        "feature_columns": ["Expiration_Date", "Unit_Price", "Category"],
        "entity_columns": ["Warehouse_Location"],
    }
    res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json=payload,
        headers=owner_user["headers"],
    )
    assert res.status_code == 400
    assert "Date column cannot also be listed as a regular feature column." in res.json()["detail"]


def test_save_config_rejects_target_column_in_feature_columns(client, owner_user):
    """Verify backend returns 400 when target_column is also included in feature_columns."""
    csv_bytes = create_grocery_style_csv()
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory_target_test.csv", csv_bytes, "text/csv")},
        data={"name": "Target Conflict Test"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    payload = {
        "task_type": "regression",
        "target_column": "Stock_Quantity",
        "date_column": None,
        "feature_columns": ["Stock_Quantity", "Unit_Price", "Category"],
    }
    res = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json=payload,
        headers=owner_user["headers"],
    )
    assert res.status_code == 400
    assert "Target column cannot also be included as a feature column." in res.json()["detail"]


def test_save_config_rejects_target_or_date_in_entity_columns(client, owner_user):
    """Verify backend returns 400 when target or date is included in entity_columns."""
    csv_bytes = create_grocery_style_csv()
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory_entity_test.csv", csv_bytes, "text/csv")},
        data={"name": "Entity Conflict Test"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Target in entity columns
    payload1 = {
        "task_type": "regression",
        "target_column": "Stock_Quantity",
        "feature_columns": ["Unit_Price", "Category"],
        "entity_columns": ["Stock_Quantity", "Warehouse_Location"],
    }
    res1 = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json=payload1,
        headers=owner_user["headers"],
    )
    assert res1.status_code == 400
    assert "Target column cannot also be included as an entity/grouping column." in res1.json()["detail"]

    # Date in entity columns
    payload2 = {
        "task_type": "forecasting",
        "target_column": "Stock_Quantity",
        "date_column": "Date_Received",
        "feature_columns": ["Unit_Price", "Category"],
        "entity_columns": ["Date_Received", "Warehouse_Location"],
    }
    res2 = client.post(
        f"/api/v1/datasets/{dataset_id}/configuration",
        json=payload2,
        headers=owner_user["headers"],
    )
    assert res2.status_code == 400
    assert "Date column cannot also be included as an entity/grouping column." in res2.json()["detail"]


def test_validate_proposed_config_catches_conflicts_and_advisory(client, owner_user):
    """Test the real-time validate-config endpoint catches date in features and produces expiration date warning."""
    csv_bytes = create_grocery_style_csv()
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory_val_test.csv", csv_bytes, "text/csv")},
        data={"name": "Realtime Val Test"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # 1. Invalid configuration with date in features
    val_res1 = client.post(
        f"/api/v1/datasets/{dataset_id}/validate-config",
        json={
            "task_type": "forecasting",
            "target_column": "Stock_Quantity",
            "date_column": "Expiration_Date",
            "feature_columns": ["Expiration_Date", "Unit_Price"],
        },
        headers=owner_user["headers"],
    )
    assert val_res1.status_code == 200
    data1 = val_res1.json()
    assert data1["is_valid"] is False
    assert any("Date column 'Expiration_Date' cannot also be listed as a regular feature column." in w for w in data1["warnings"])

    # 2. Valid configuration without date in features, but with Expiration_Date as date_column
    val_res2 = client.post(
        f"/api/v1/datasets/{dataset_id}/validate-config",
        json={
            "task_type": "forecasting",
            "target_column": "Stock_Quantity",
            "date_column": "Expiration_Date",
            "feature_columns": ["Unit_Price", "Category"],
        },
        headers=owner_user["headers"],
    )
    assert val_res2.status_code == 200
    data2 = val_res2.json()
    assert data2["is_valid"] is True
    # Advisory warning exists and suggests genuine observation dates
    assert any("appears to represent product shelf-life expiration" in w for w in data2["warnings"])
    assert any("Last_Order_Date" in w or "Date_Received" in w for w in data2["warnings"])


def test_training_start_rejects_conflicting_configuration(client, owner_user, db):
    """Verify POST /api/v1/training/start rejects runs if configuration has date in features."""
    csv_bytes = create_grocery_style_csv()
    upload_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("inventory_train_test.csv", csv_bytes, "text/csv")},
        data={"name": "Train Conflict Test"},
        headers=owner_user["headers"],
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Manually inject an invalid configuration in the DB to test training start guard
    invalid_config = DatasetConfiguration(
        company_id=owner_user["company"].id,
        dataset_id=dataset_id,
        task_type="forecasting",
        target_column="Stock_Quantity",
        date_column="Expiration_Date",
        feature_columns=["Expiration_Date", "Unit_Price"],
        configuration_version=1,
    )
    db.add(invalid_config)
    db.commit()

    train_res = client.post(
        "/api/v1/training/start",
        json={"dataset_id": dataset_id, "task_type": "forecasting"},
        headers=owner_user["headers"],
    )
    assert train_res.status_code == 400
    assert "Date column 'Expiration_Date' cannot also be listed as a regular feature column." in train_res.json()["detail"]
