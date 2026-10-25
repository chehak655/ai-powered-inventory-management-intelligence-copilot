from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import WorkspaceContext, get_current_workspace
from app.models.dataset import Dataset
from app.services.inventory.inventory_service import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory Analytics & Intelligence"])


@router.get(
    "/kpis",
    summary="Get inventory KPIs, safety stock, and reorder points for a dataset",
)
def get_inventory_kpis(
    dataset_id: Optional[str] = Query(None),
    service_level: float = Query(0.95, ge=0.5, le=0.999),
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Compute inventory KPIs, Safety Stock (Z * sigma * sqrt(L)), Reorder Point ((d * L) + SS),
    and stockout risk classifications for a company dataset.
    """
    target_dataset_id = dataset_id
    if not target_dataset_id:
        first_ds = (
            db.query(Dataset)
            .filter(Dataset.company_id == ctx.company.id, Dataset.is_deleted == False)
            .order_by(Dataset.created_at.desc())
            .first()
        )
        if not first_ds:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No datasets found in this company workspace.",
            )
        target_dataset_id = first_ds.id

    # Compute Z factor from service level
    # 0.95 -> 1.65, 0.90 -> 1.28, 0.99 -> 2.33
    z = 1.65
    if service_level >= 0.99:
        z = 2.33
    elif service_level >= 0.975:
        z = 1.96
    elif service_level >= 0.95:
        z = 1.65
    elif service_level >= 0.90:
        z = 1.28

    return inventory_service.compute_inventory_kpis(
        db=db,
        company_id=ctx.company.id,
        dataset_id=target_dataset_id,
        service_level_z=z,
    )
