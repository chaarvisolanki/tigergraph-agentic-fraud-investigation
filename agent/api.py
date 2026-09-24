from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .models import CaseRecord, Trigger


def create_app(agent) -> FastAPI:
    app = FastAPI(title="Agentic Fraud Investigation API")
    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    if ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=ui_dir, html=True), name="ui")

    @app.post("/investigations", response_model=CaseRecord)
    async def create_investigation(trigger: Trigger) -> CaseRecord:
        case = await agent.investigate(trigger)
        answers_dir = Path(__file__).resolve().parent.parent / "answers"
        answers_dir.mkdir(exist_ok=True)
        (answers_dir / f"{case.case_id}.json").write_text(
            case.model_dump_json(indent=2), encoding="utf-8"
        )
        return case

    @app.get("/")
    async def dashboard():
        return {"dashboard": "/ui/index.html", "api": "/investigations"}

    return app
