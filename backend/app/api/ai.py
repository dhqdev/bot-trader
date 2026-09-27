"""Status da IA. A análise por conversa foi retirada: a IA trabalha por trás
(recomendação do robô, notícias e piloto automático)."""

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.services.llm import resolve_ai

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)):
    ai = resolve_ai(user.id)
    if ai is None:
        return {"configured": False, "provider": None, "provider_label": None, "model": None}
    return {"configured": True, "provider": ai.provider, "provider_label": ai.label, "model": ai.model}
