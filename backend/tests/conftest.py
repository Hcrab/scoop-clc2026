"""Ordinary regression tests must never spend real provider allowance."""
from dataclasses import replace
import pytest


@pytest.fixture(autouse=True)
def offline_assistant(monkeypatch):
    from scoop.ai import chat
    monkeypatch.setattr(chat,'settings',replace(chat.settings,llm_provider='scripted'))
