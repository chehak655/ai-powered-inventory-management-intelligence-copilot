from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.workspaces import router as workspaces_router
from app.api.v1.datasets import router as datasets_router
from app.api.v1.training import router as training_router
from app.api.v1.models import router as models_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.copilot import router as copilot_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(workspaces_router)
api_v1_router.include_router(datasets_router)
api_v1_router.include_router(training_router)
api_v1_router.include_router(models_router)
api_v1_router.include_router(predictions_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(copilot_router)

__all__ = ["api_v1_router"]
