import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base, Repo, Retrain
from monitoring.retrain_trigger import check_circuit_breaker, trigger_retrain, MAX_AUTO_RETRAINS_PER_24H


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    repo = Repo(
        id="test_repo_1",
        sequential_id=1,
        repo_name="test-repo",
        github_url="https://github.com/user/test-repo",
        owner="user",
        is_deployed=True
    )
    session.add(repo)
    session.commit()

    yield session
    session.close()


def test_circuit_breaker_allows_under_limit(test_db):
    is_allowed, count = check_circuit_breaker("test_repo_1", db=test_db)
    assert is_allowed is True
    assert count == 0


def test_circuit_breaker_trips_at_limit(test_db):
    # Simulate 3 previous auto retrains within the last hour
    for i in range(MAX_AUTO_RETRAINS_PER_24H):
        r = Retrain(
            repo_id="test_repo_1",
            triggered_at=datetime.utcnow() - timedelta(minutes=10 * (i + 1)),
            trigger_reason="drift",
            status="triggered"
        )
        test_db.add(r)
    test_db.commit()

    is_allowed, count = check_circuit_breaker("test_repo_1", db=test_db)
    assert is_allowed is False
    assert count == 3
