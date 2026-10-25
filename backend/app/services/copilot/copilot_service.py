import json
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.training import CandidateModel, TrainingRun
from app.services.inventory.inventory_service import inventory_service


class CopilotService:
    @classmethod
    def assemble_grounded_context(cls, db: Session, company_id: str) -> Dict[str, Any]:
        """Collect all live tenant context: datasets, active models, metrics, and inventory KPIs."""
        datasets = (
            db.query(Dataset)
            .filter(Dataset.company_id == company_id, Dataset.is_deleted == False)
            .all()
        )
        ds_summary = [
            {
                "id": d.id,
                "name": d.name,
                "rows": d.row_count,
                "columns": d.column_count,
                "health_score": d.validation_summary.get("health_score") if d.validation_summary else None,
            }
            for d in datasets
        ]

        active_models = (
            db.query(CandidateModel)
            .filter(CandidateModel.company_id == company_id, CandidateModel.is_active == True)
            .all()
        )
        models_summary = [
            {
                "id": m.id,
                "algorithm": m.algorithm_display_name,
                "family": m.model_family,
                "dataset_id": m.dataset_id,
                "metrics": m.metrics,
                "created_at": str(m.created_at),
            }
            for m in active_models
        ]

        # Gather inventory metrics for first available dataset
        inventory_kpis = None
        if len(datasets) > 0:
            try:
                inventory_kpis = inventory_service.compute_inventory_kpis(db, company_id, datasets[0].id)
            except Exception:
                inventory_kpis = None

        return {
            "datasets": ds_summary,
            "active_models": models_summary,
            "inventory": inventory_kpis,
        }

    @classmethod
    async def query(cls, db: Session, company_id: str, prompt: str) -> Dict[str, Any]:
        """Generate grounded answer using Gemini LLM if configured, or deterministic grounded engine."""
        context = cls.assemble_grounded_context(db, company_id)
        prompt_lower = prompt.lower()

        grounded_sources: List[str] = []
        if context["datasets"]:
            grounded_sources.extend([f"Dataset: {d['name']}" for d in context["datasets"][:2]])
        if context["active_models"]:
            grounded_sources.extend([f"Active Model: {m['algorithm']}" for m in context["active_models"][:2]])
        if context["inventory"]:
            grounded_sources.append(f"Inventory Health: {context['inventory']['summary']['total_skus']} SKUs")

        # 1. If Gemini API key is configured, call Gemini API with grounded context
        if settings.GEMINI_API_KEY:
            try:
                system_context = (
                    "You are AI Powered Inventory Management and Intelligence Copilot, an expert AI inventory supply chain analyst and data scientist. "
                    "You are answering questions for a business based EXCLUSIVELY on their real company data provided in this JSON:\n"
                    f"{json.dumps(context, indent=2)}\n\n"
                    "Instructions:\n"
                    "- Provide concise, highly accurate, professional answers formatted in Markdown.\n"
                    "- State numbers, SKU names, model accuracy metrics, and reorder quantities exactly as given in the context.\n"
                    "- Highlight actionable operational next steps.\n"
                )

                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
                payload = {
                    "contents": [
                        {"role": "user", "parts": [{"text": f"{system_context}\n\nUser Question: {prompt}"}]}
                    ],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000},
                }

                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        text_output = data["candidates"][0]["parts"][0]["text"]
                        return {
                            "answer": text_output,
                            "grounded_sources": grounded_sources,
                            "model_engine": "Gemini 1.5 Flash (Grounded)",
                        }
            except Exception as e:
                # Fall through to deterministic engine on API error
                pass

        # 2. Deterministic Grounded Business Intelligence Engine
        inv = context.get("inventory")
        items = inv.get("items", []) if inv else []
        summary = inv.get("summary", {}) if inv else {}
        critical_items = [i for i in items if i["status"] == "CRITICAL"]
        reorder_items = [i for i in items if i["status"] == "REORDER_NOW"]
        overstock_items = [i for i in items if i["status"] == "OVERSTOCK"]

        if any(w in prompt_lower for w in ["stockout", "critical", "shortage", "risk", "out of stock"]):
            if critical_items or reorder_items:
                critical_lines = [
                    f"- **{i['sku']}**: Current Stock = `{i['current_stock']}` units | ROP = `{i['reorder_point']}` | **Days of Supply = {i['days_of_supply']} days** (Recommend reordering `{i['recommended_reorder_qty']}` units)"
                    for i in (critical_items + reorder_items)[:6]
                ]
                answer = (
                    f"### ⚠️ Stockout & Reorder Risk Assessment\n\n"
                    f"Our inventory analysis detected **{len(critical_items)} critical stockout risks** and **{len(reorder_items)} items below reorder point**.\n\n"
                    f"**Urgent Action Required:**\n"
                    + "\n".join(critical_lines)
                    + f"\n\n**Operational Recommendation**: Expedite purchase orders with your suppliers for these SKUs to prevent lost sales."
                )
            else:
                answer = "### ✅ Stockout Risk Assessment\n\nAll inventory levels are currently healthy. No items are below their calculated Safety Stock or Reorder Points."

        elif any(w in prompt_lower for w in ["overstock", "excess", "capital", "cash"]):
            if overstock_items:
                over_lines = [
                    f"- **{i['sku']}**: Current Stock = `{i['current_stock']}` | Healthy Max = `{round(i['reorder_point'] * 2.5)}` | **Capital at Risk = ${i['overstock_capital']:,.2f}**"
                    for i in overstock_items[:5]
                ]
                total_risk = summary.get("overstock_capital_at_risk", 0.0)
                answer = (
                    f"### 📦 Overstock & Capital Allocation Analysis\n\n"
                    f"You have **{len(overstock_items)} overstocked products** representing **${total_risk:,.2f}** in trapped working capital.\n\n"
                    f"**Top Excess Items:**\n"
                    + "\n".join(over_lines)
                    + f"\n\n**Recommendation**: Consider promotional bundling or discount campaigns to release trapped liquidity."
                )
            else:
                answer = "### 📦 Overstock Analysis\n\nNo significant overstock detected. Inventory turnover is well-balanced across all catalog items."

        elif any(w in prompt_lower for w in ["model", "algorithm", "accuracy", "champion", "machine learning", "rmse", "mae"]):
            active = context.get("active_models", [])
            if active:
                m = active[0]
                metrics_str = ", ".join(f"`{k.upper()}: {v:.4f}`" for k, v in (m.get("metrics") or {}).items() if isinstance(v, (int, float)))
                answer = (
                    f"### 🏆 Machine Learning Production Champion\n\n"
                    f"The active production model is **{m['algorithm']}** (`{m['family']}` family).\n\n"
                    f"- **Model ID**: `{m['id']}`\n"
                    f"- **Validation Metrics**: {metrics_str}\n"
                    f"- **Deployment Status**: Active & Serving Inferences\n\n"
                    f"This model was evaluated against other candidate algorithms and achieved the optimal validation score."
                )
            else:
                answer = "### 🤖 Model Status\n\nNo active production model is currently deployed. Train candidate models in the **Model Lab** to select a champion."

        elif any(w in prompt_lower for w in ["reorder", "purchase", "order", "buy", "replenish"]):
            reorders = [i for i in items if i["recommended_reorder_qty"] > 0]
            if reorders:
                r_lines = [
                    f"- **{i['sku']}**: Order **`{i['recommended_reorder_qty']}` units** (Lead time: {i['lead_time_days']} days, Unit Cost: ${i['unit_cost']:.2f})"
                    for i in reorders[:5]
                ]
                total_order_cost = sum(i["recommended_reorder_qty"] * i["unit_cost"] for i in reorders)
                answer = (
                    f"### 🛒 Replenishment & Reorder Plan\n\n"
                    f"Based on 95% service-level safety stocks and lead times, we recommend ordering **{len(reorders)} SKUs** totaling **${total_order_cost:,.2f}**:\n\n"
                    + "\n".join(r_lines)
                    + f"\n\nPlacing these orders now ensures continuity before safety buffers deplete."
                )
            else:
                answer = "### 🛒 Replenishment Plan\n\nNo orders are needed right now. All SKUs are above their respective Reorder Points."

        else:
            # Executive Summary Briefing
            ds_count = len(context.get("datasets", []))
            active_m_count = len(context.get("active_models", []))
            total_skus = summary.get("total_skus", 0)
            total_val = summary.get("total_inventory_value", 0.0)
            crit = summary.get("critical_stockouts", 0)

            answer = (
                f"### 📊 Workspace Executive Briefing\n\n"
                f"- **Data Assets**: `{ds_count}` datasets uploaded and verified\n"
                "- **Machine Learning**: "
                + (f"`{active_m_count}` active production models deployed" if active_m_count else "No models promoted yet")
                + f"\n- **Inventory Footprint**: `{total_skus}` SKUs tracked with a total value of **${total_val:,.2f}**\n"
                f"- **Health Status**: `{crit}` critical stockout alerts active\n\n"
                f"Ask me about specific stockout risks, model performance metrics, or recommended replenishment quantities!"
            )

        return {
            "answer": answer,
            "grounded_sources": grounded_sources,
            "model_engine": "Deterministic Supply Chain Expert Engine (Grounded)",
        }


copilot_service = CopilotService()
