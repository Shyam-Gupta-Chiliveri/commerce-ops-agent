from __future__ import annotations

import httpx
import pytest

from opsagent.mockapi.app import create_app
from opsagent.settings import load_settings
from opsagent.sync_asgi import SyncASGITransport
from opsagent.warehouse.load import sync


@pytest.fixture
def settings():
    return load_settings()


@pytest.fixture
def http(settings):
    app = create_app(settings)
    return httpx.Client(transport=SyncASGITransport(app), base_url="http://mock")


@pytest.fixture
def synced(http, settings, tmp_path):
    db = tmp_path / "warehouse.sqlite"
    stats = sync(http, settings, db)
    return http, settings, db, stats
