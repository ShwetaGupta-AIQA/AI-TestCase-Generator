import os
import unittest
from unittest.mock import patch

from runs.database import database_url


class DatabaseUrlTests(unittest.TestCase):
    def test_render_postgres_urls_use_psycopg_v3(self):
        for supplied in ("postgres://user:pass@host:5432/db",
                         "postgresql://user:pass@host:5432/db"):
            with self.subTest(supplied=supplied), patch.dict(os.environ, {"DATABASE_URL": supplied}, clear=False):
                self.assertEqual(database_url(), "postgresql+psycopg://user:pass@host:5432/db")


if __name__ == "__main__":
    unittest.main()
