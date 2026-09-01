import os
import tempfile

import pytest

os.environ["AUTH_DISABLED"] = "1"
_test_db = os.path.join(tempfile.gettempdir(), "nexivoreach_test.db")
if os.path.exists(_test_db):
    os.remove(_test_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"


@pytest.fixture(autouse=True)
def _init_test_db():
    from app.database.session import init_db
    init_db()
