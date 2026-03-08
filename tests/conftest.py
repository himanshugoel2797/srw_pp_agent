"""Shared fixtures for tests."""

import pytest

from srw_pp_agent.session import TuningSession
from tests.mocks.srw_mock import SAMPLE_BEAMLINE


@pytest.fixture
def session():
    """Create a fresh TuningSession."""
    return TuningSession()


@pytest.fixture
def sample_beamline():
    """Return a sample beamline definition."""
    return dict(SAMPLE_BEAMLINE)
