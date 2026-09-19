import pytest

from app.domain.spellcheck.service import register_dictionaries


@pytest.fixture(scope="session", autouse=True)
def dictionaries():
    register_dictionaries()
