import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.state import STATE


@pytest.fixture(autouse=True)
def fresh_state():
    """Every test starts from a clean scenario session."""
    STATE.reset()
    yield
    STATE.reset()
