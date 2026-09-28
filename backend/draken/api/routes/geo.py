"""AI visibility (GEO): prompt sets, runs, summary, llms.txt and schema assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import get_project
from draken.core.config import settings
from draken.core.database import get_db
from draken.core.models import AIPrompt, AIVisibilityRun, Project
from draken.core.schemas import (
    AIPromptIn,
    AIPromptOut,
    AIVisibilityRunOut,
    GeneratePromptsRequest,
    RunAIVisibilityRequest,
)
from draken.engines.geo import engines as engine_mod
from draken.engines.scheduler import jobs
from draken.services import geo as geo_service

router = APIRouter(prefix="/api/projects/{project_id}/ai", tags=["ai visibility"])


@router.get("/engines")
def engines(_project: Project = Depends(get_project)):
    configured = settings.ai_engines_configured()
    return {
        "configured": configured,
        "available": engine_mod.available_engines(),
        "any_configured": any(configured.values()),
        "setup_hint": (
            "Add one or more of DRAKEN_ANTHROPIC_API_KEY, DRAKEN_OPENAI_API_KEY, "
            "DRAKEN_PERPLEXITY_API_KEY, DRAKEN_GEMINI_API_KEY to .env and restart. "
            "Perplexity is the most informative because it returns its grounding sources."
        ),
    }


@router.get("/prompts", response_model=list[AIPromptOut])
def list_prompts(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    category: str = "",
    active_only: bool = True,
):
    query = select(AIPrompt).where(AIPrompt.project_id == project.id)
    if category:
        query = query.where(AIPrompt.category == category)
    if active_only:
        query = query.where(AIPrompt.is_active.is_(True))
    return list(db.execute(query.order_by(AIPrompt.priority, AIPrompt.id)).scalars())


@router.post("/prompts", response_model=AIPromptOut, status_code=201)
def create_prompt(
    payload: AIPromptIn,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    prompt = AIPrompt(
        project_id=project.id,
        prompt=payload.prompt,
        category=payload.category,
        intent=payload.intent,
        language=payload.language,
        priority=payload.priority,
    )
    db.add(prompt)
    db.commit()
    return prompt


@router.post("/prompts/generate")
def generate_prompts(
    payload: GeneratePromptsRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Build the prompt set a real buyer would type, from your keywords and profile."""
    return geo_service.generate_prompt_set(
        db,
        project=project,
        from_keywords=payload.from_keywords,
        limit=payload.limit,
        extra_topics=payload.extra_topics,
    )


@router.delete("/prompts/{prompt_id}", status_code=204)
def delete_prompt(
    prompt_id: int, project: Project = Depends(get_project), db: Session = Depends(get_db)
):
    prompt = db.get(AIPrompt, prompt_id)
    if prompt is None or prompt.project_id != project.id:
        raise HTTPException(status_code=404, detail="Prompt not found in this project")
    db.delete(prompt)
    db.commit()


@router.post("/run")
def run_visibility(
    payload: RunAIVisibilityRequest,
    project: Project = Depends(get_project),
):
    """Ask each configured engine the prompt set (runs in background)."""
    if not any(settings.ai_engines_configured().values()):
        raise HTTPException(
            status_code=422,
            detail=(
                "No AI engine is configured. Add at least one API key "
                "(DRAKEN_ANTHROPIC_API_KEY, DRAKEN_OPENAI_API_KEY, DRAKEN_PERPLEXITY_API_KEY "
                "or DRAKEN_GEMINI_API_KEY) and restart."
            ),
        )
    job_id = jobs.enqueue_and_spawn(
        kind="ai_visibility",
        project_id=project.id,
        params={
            "engines": payload.engines or None,
            "prompt_ids": payload.prompt_ids or None,
            "limit": payload.limit,
        },
    )
    return {"job_id": job_id, "state": "queued"}


@router.get("/summary")
def summary(
    days: int = Query(30, ge=1, le=365),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return geo_service.summary(db, project=project, days=days)


@router.get("/runs", response_model=list[AIVisibilityRunOut])
def list_runs(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    engine: str = "",
    prompt_id: int | None = None,
    mentioned_only: bool = False,
    limit: int = Query(100, ge=1, le=1000),
):
    query = select(AIVisibilityRun).where(AIVisibilityRun.project_id == project.id)
    if engine:
        query = query.where(AIVisibilityRun.engine == engine)
    if prompt_id is not None:
        query = query.where(AIVisibilityRun.prompt_id == prompt_id)
    if mentioned_only:
        query = query.where(AIVisibilityRun.brand_mentioned.is_(True))
    return list(
        db.execute(query.order_by(AIVisibilityRun.captured_at.desc()).limit(limit)).scalars()
    )


@router.get("/assets")
def assets(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """Generate llms.txt and the JSON-LD bundle for this project."""
    return geo_service.geo_assets(db, project=project)


@router.get("/assets/llms.txt")
def llms_txt(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    data = geo_service.geo_assets(db, project=project)
    return Response(
        content=data["llms_txt"],
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="llms.txt"'},
    )


@router.post("/entity-consistency")
def entity_consistency(
    listings: list[dict] | None = None,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Compare your canonical NAP against what live listings actually say."""
    return geo_service.entity_consistency(db, project=project, listings=listings)
