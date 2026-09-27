import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, session_scope
from app.deps import get_current_user
from app.models import AIReport, User
from app.schemas import ChatIn
from app.services.ai import stream_chat
from app.services.llm import resolve_ai

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)):
    ai = resolve_ai(user.id)
    if ai is None:
        return {"configured": False, "provider": None, "provider_label": None, "model": None}
    return {"configured": True, "provider": ai.provider, "provider_label": ai.label, "model": ai.model}


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(get_current_user)):
    ai = resolve_ai(user.id)
    if ai is None:
        raise HTTPException(400, "Cadastre uma chave de IA (Claude ou GPT) em Configurações para usar a análise.")
    user_id = user.id
    messages = [m.model_dump() for m in body.messages]

    async def events():
        answer: list[str] = []
        model = ""
        async for event in stream_chat(ai, user_id, messages, body.context.bot_id, body.context.backtest):
            if event["type"] == "text":
                answer.append(event["text"])
            if event["type"] == "done":
                model = event.get("model", "")
                if body.save_report and answer:
                    question = messages[-1]["content"]
                    with session_scope() as db:
                        report = AIReport(
                            user_id=user_id,
                            bot_id=body.context.bot_id,
                            title=(body.title or question)[:200],
                            question=question,
                            content="".join(answer),
                            model=model,
                        )
                        db.add(report)
                        db.flush()
                        event["report_id"] = report.id
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/reports")
def list_reports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AIReport).where(AIReport.user_id == user.id).order_by(AIReport.id.desc()).limit(100))
    return [
        {"id": r.id, "title": r.title, "bot_id": r.bot_id, "model": r.model, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


def _own_report(report_id: int, user: User, db: Session) -> AIReport:
    report = db.get(AIReport, report_id)
    if report is None or report.user_id != user.id:
        raise HTTPException(404, "Relatório não encontrado")
    return report


@router.get("/reports/{report_id}")
def get_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _own_report(report_id, user, db)
    return {
        "id": r.id,
        "title": r.title,
        "question": r.question,
        "content": r.content,
        "bot_id": r.bot_id,
        "model": r.model,
        "created_at": r.created_at.isoformat(),
    }


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_own_report(report_id, user, db))
    db.commit()
    return {"ok": True}
