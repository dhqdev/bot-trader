import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, session_scope
from app.deps import get_current_user
from app.models import AIReport, User
from app.schemas import ChatIn
from app.services.ai import chat_stream, resolve_api_key

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
def ai_status(user: User = Depends(get_current_user)):
    return {"configured": bool(resolve_api_key(user.id)), "model": get_settings().ai_model}


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(get_current_user)):
    api_key = resolve_api_key(user.id)
    if not api_key:
        raise HTTPException(400, "Configure a chave da Anthropic em Configurações para usar a IA.")
    user_id = user.id
    messages = [m.model_dump() for m in body.messages]

    async def events():
        answer: list[str] = []
        model = ""
        async for event in chat_stream(user_id, api_key, messages, body.context.bot_id, body.context.backtest):
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
