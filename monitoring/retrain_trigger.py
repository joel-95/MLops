import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.db.models import SessionLocal, Retrain, Repo
from monitoring.alerts import send_alert
from github_app.app_config import dispatch_repository_event, generate_installation_token

MAX_AUTO_RETRAINS_PER_24H = int(os.getenv("MAX_AUTO_RETRAINS_PER_24H", 3))


def check_circuit_breaker(repo_id: str, db: Optional[Session] = None) -> Tuple_CB:
    """
    Checks if the repository has exceeded the 24-hour auto-retrain limit.
    Returns (is_allowed: bool, count_last_24h: int)
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        since_time = datetime.utcnow() - timedelta(hours=24)
        count = (
            db.query(Retrain)
            .filter(
                Retrain.repo_id == repo_id,
                Retrain.triggered_at >= since_time,
                Retrain.status != "blocked"
            )
            .count()
        )
        is_allowed = count < MAX_AUTO_RETRAINS_PER_24H
        return is_allowed, count
    finally:
        if should_close:
            db.close()


Tuple_CB = tuple[bool, int]


def trigger_retrain(
    repo_id: str,
    reason: str = "drift",
    details: Optional[Dict[str, Any]] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    Triggers an automated retraining run via GitHub Actions repository_dispatch,
    guarded by the 24-hour circuit breaker.

    Args:
        repo_id: Repository ID
        reason: Cause for retrain ('drift', 'anomaly', 'drift+anomaly', 'manual')
        details: Optional dict with drifted column names or anomaly rates
        force: If True, bypasses the circuit breaker (for manual user overrides)

    Returns:
        Dict detailing whether retrain was dispatched or blocked by circuit breaker
    """
    db = SessionLocal()
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        repo_name = repo.repo_name if repo else repo_id
        owner = repo.owner if repo else "unknown"

        # Check circuit breaker unless forced by human
        is_allowed, recent_count = check_circuit_breaker(repo_id, db=db)

        if not is_allowed and not force:
            # Trip circuit breaker!
            blocked_record = Retrain(
                repo_id=repo_id,
                trigger_reason=reason,
                status="blocked",
                triggered_at=datetime.utcnow()
            )
            db.add(blocked_record)
            db.commit()

            alert_msg = (
                f"🚨 **CIRCUIT BREAKER TRIPPED** for `{repo_name}` (`{repo_id}`)!\n"
                f"Reason: {recent_count} auto-retrains triggered within the last 24 hours "
                f"(limit is {MAX_AUTO_RETRAINS_PER_24H}).\n"
                f"Underlying production data may be fundamentally corrupt or anomalous.\n"
                f"**Automated retraining halted.** Human intervention required via Dashboard or `POST /repos/{repo_id}/retrain`."
            )
            send_alert(alert_msg, severity="critical", title="Circuit Breaker Engaged")

            return {
                "triggered": False,
                "circuit_breaker_tripped": True,
                "reason": "circuit_breaker_limit_exceeded",
                "retrain_count_24h": recent_count,
                "limit": MAX_AUTO_RETRAINS_PER_24H
            }

        # Record new retrain
        retrain_record = Retrain(
            repo_id=repo_id,
            trigger_reason=reason if not force else f"manual_override({reason})",
            status="triggered",
            triggered_at=datetime.utcnow()
        )
        db.add(retrain_record)
        db.commit()

        # Fire GitHub repository_dispatch
        token = generate_installation_token(repo_id)
        dispatch_payload = {
            "repo_id": repo_id,
            "trigger_reason": reason,
            "force": force,
            "retrain_id": retrain_record.id,
            "details": details or {}
        }

        dispatch_result = dispatch_repository_event(
            repo_owner=owner,
            repo_name=repo_name,
            event_type="automlops-retrain",
            client_payload=dispatch_payload,
            token=token
        )

        send_alert(
            f"🔄 Automated retraining triggered for `{repo_name}`.\n"
            f"Reason: **{reason}** | Attempt: **{recent_count + 1}/{MAX_AUTO_RETRAINS_PER_24H}** in 24h window.",
            severity="warning"
        )

        return {
            "triggered": True,
            "circuit_breaker_tripped": False,
            "retrain_id": retrain_record.id,
            "retrain_count_24h": recent_count + 1,
            "dispatch_result": dispatch_result
        }

    finally:
        db.close()
