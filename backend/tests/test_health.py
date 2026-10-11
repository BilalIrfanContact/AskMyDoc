import unittest
from unittest.mock import patch

import httpx

from backend.services.persistence.common import PersistenceError


def _main_module():
    # Other tests re-import backend.main, so look it up at call time to patch the live app.
    import backend.main

    return backend.main


class HealthCheckTests(unittest.IsolatedAsyncioTestCase):
    async def _get_health(self) -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_main_module().app), base_url="http://test") as client:
            return await client.get("/health")

    async def test_reports_ok_after_reading_the_database(self):
        with patch.object(_main_module(), "ping_database") as ping:
            response = await self._get_health()

        ping.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_reports_unavailable_when_the_database_cannot_be_reached(self):
        with patch.object(_main_module(), "ping_database", side_effect=PersistenceError("down")):
            response = await self._get_health()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "database_unavailable"})


if __name__ == "__main__":
    unittest.main()
