from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Agent, Run
from app.db.session import get_db
from app.schemas.agents import CrewRunRequest, RunOut, RunRequest
from app.services.crew_engine import CrewEngine

router = APIRouter(prefix="/runs", tags=["runs"])
engine = CrewEngine()


@router.post("/agent", response_model=RunOut)
def run_agent(payload: RunRequest, db: Session = Depends(get_db)) -> RunOut:
    agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    run = Run(
        run_type="agent",
        agent_id=agent.id,
        input_payload={
            "input_text": payload.input_text,
            "context": payload.context,
            "mode": payload.mode,
        },
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = engine.run_agent(
            {
                "name": agent.name,
                "role": agent.role,
                "goal": agent.goal,
                "model": agent.model,
            },
            payload.input_text,
            payload.context,
        )
        run.status = "completed"
        run.output_payload = result
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
    finally:
        db.commit()
        db.refresh(run)

    return run


@router.post("/crew", response_model=RunOut)
def run_crew(payload: CrewRunRequest, db: Session = Depends(get_db)) -> RunOut:
    agents = db.query(Agent).filter(Agent.id.in_(payload.agent_ids)).all()
    if len(agents) != len(payload.agent_ids):
        raise HTTPException(status_code=404, detail="One or more agents not found")

    run = Run(
        run_type="crew",
        crew_name=payload.crew_name or "default-crew",
        input_payload={
            "objective": payload.objective,
            "context": payload.context,
            "mode": payload.mode,
            "agent_ids": [str(agent.id) for agent in agents],
        },
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = engine.run_crew(
            [
                {
                    "name": agent.name,
                    "role": agent.role,
                    "goal": agent.goal,
                    "model": agent.model,
                }
                for agent in agents
            ],
            payload.objective,
            payload.context,
            payload.crew_name,
        )
        run.status = "completed"
        run.output_payload = result
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
    finally:
        db.commit()
        db.refresh(run)

    return run


@router.get("", response_model=list[RunOut])
def list_runs(db: Session = Depends(get_db)) -> list[RunOut]:
    return db.query(Run).order_by(Run.created_at.desc()).all()


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db)) -> RunOut:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run