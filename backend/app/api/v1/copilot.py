from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import WorkspaceContext, get_current_workspace
from app.services.copilot.copilot_service import copilot_service

router = APIRouter(prefix="/copilot", tags=["AI Copilot"])


class CopilotQueryRequest(BaseModel):
    prompt: str


class CopilotQueryResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    answer: str
    grounded_sources: List[str]
    model_engine: str


@router.post(
    "/query",
    response_model=CopilotQueryResponse,
    summary="Ask Copilot a natural language question grounded in company data",
)
async def query_copilot(
    payload: CopilotQueryRequest,
    ctx: WorkspaceContext = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    """
    Process conversational questions about inventory health, stockouts, model accuracy,
    and dataset quality grounded in real company workspace data.
    """
    res = await copilot_service.query(db=db, company_id=ctx.company.id, prompt=payload.prompt)
    return CopilotQueryResponse(**res)


@router.get(
    "/prompts",
    response_model=List[str],
    summary="Get recommended conversational prompt questions",
)
def get_recommended_prompts():
    """Return contextual prompt starter chips for the Copilot interface."""
    return [
        "Which SKUs are at critical risk of stockout?",
        "What is our active champion model and its validation accuracy?",
        "How much working capital is trapped in overstocked inventory?",
        "Show me replenishment and reorder recommendations for this week.",
        "Provide an executive briefing of our workspace data and inventory health.",
    ]
