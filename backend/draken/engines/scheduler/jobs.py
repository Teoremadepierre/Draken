"""In-process background jobs backed by the ``jobs`` table.

Deliberately not Celery: Draken is a single-node internal tool, and a DB-backed
task table plus asyncio is enough to run audits, expansions and AI-visibility
sweeps without adding a broker to operate.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Awaitable, Callable

from draken.core.database import session_scope
from draken.core.logging import get_logger
from draken.core.models import Job, JobState, utcnow

log = get_logger(__name__)

JobHandler = Callable[[int, dict], Awaitable[dict]]
_REGISTRY: dict[str, JobHandler] = {}
_RUNNING: dict[int, asyncio.Task] = {}


def register(kind: str) -> Callable[[JobHandler], JobHandler]:
    def decorator(fn: JobHandler) -> JobHandler:
        _REGISTRY[kind] = fn
        return fn

    return decorator


def registered_kinds() -> list[str]:
    return sorted(_REGISTRY)


def enqueue(*, kind: str, project_id: int | None = None, params: dict | None = None) -> int:
    """Create a pending job row and return its id."""
    if kind not in _REGISTRY:
        raise ValueError(f"unknown job kind: {kind!r} (known: {', '.join(registered_kinds())})")
    with session_scope() as db:
        job = Job(kind=kind, project_id=project_id, params=params or {}, state=JobState.pending.value)
        db.add(job)
        db.flush()
        return job.id


async def run_job(job_id: int) -> None:
    """Execute one job, recording state, progress and result."""
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            log.warning("job %s vanished before it could run", job_id)
            return
        if job.state != JobState.pending.value:
            return
        kind, params, project_id = job.kind, dict(job.params or {}), job.project_id
        job.state = JobState.running.value
        job.started_at = utcnow()
        job.message = "running"

    handler = _REGISTRY.get(kind)
    if handler is None:
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job:
                job.state = JobState.failed.value
                job.error = f"no handler registered for {kind!r}"
                job.finished_at = utcnow()
        return

    try:
        result = await handler(project_id or 0, params)
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job:
                job.state = JobState.succeeded.value
                job.result = result or {}
                job.progress = 1.0
                job.message = "done"
                job.finished_at = utcnow()
        log.info("job %s (%s) succeeded", job_id, kind)
    except Exception as exc:  # noqa: BLE001
        log.error("job %s (%s) failed: %s", job_id, kind, exc)
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job:
                job.state = JobState.failed.value
                job.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"
                job.finished_at = utcnow()
    finally:
        _RUNNING.pop(job_id, None)


def spawn(job_id: int) -> None:
    """Fire-and-forget a job on the running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.warning("no running event loop; job %s stays pending", job_id)
        return
    task = loop.create_task(run_job(job_id))
    _RUNNING[job_id] = task
    task.add_done_callback(lambda t: _RUNNING.pop(job_id, None))


def enqueue_and_spawn(*, kind: str, project_id: int | None = None, params: dict | None = None) -> int:
    job_id = enqueue(kind=kind, project_id=project_id, params=params)
    spawn(job_id)
    return job_id


def update_progress(job_id: int, progress: float, message: str = "") -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job:
            job.progress = max(0.0, min(1.0, progress))
            if message:
                job.message = message[:500]


def cancel(job_id: int) -> bool:
    task = _RUNNING.get(job_id)
    if task and not task.done():
        task.cancel()
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job and job.state in {JobState.pending.value, JobState.running.value}:
            job.state = JobState.cancelled.value
            job.finished_at = utcnow()
            return True
    return False


async def resume_pending(limit: int = 5) -> int:
    """On startup, pick up jobs left pending by a restart."""
    from sqlalchemy import select

    with session_scope() as db:
        pending = list(
            db.execute(
                select(Job.id).where(Job.state == JobState.pending.value).order_by(Job.id).limit(limit)
            ).scalars()
        )
        # A job stuck in 'running' across a restart is not actually running.
        stuck = list(
            db.execute(select(Job).where(Job.state == JobState.running.value)).scalars()
        )
        for job in stuck:
            job.state = JobState.pending.value
            job.message = "requeued after restart"
            pending.append(job.id)

    for job_id in pending[:limit]:
        spawn(job_id)
    return len(pending[:limit])
