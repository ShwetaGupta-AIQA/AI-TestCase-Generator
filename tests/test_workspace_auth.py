import os
import unittest
from unittest.mock import patch

from services.workspace_auth import issue_workspace, verify_workspace


class WorkspaceAuthTests(unittest.TestCase):
    def test_issued_token_verifies_and_tampering_is_rejected(self):
        with patch.dict(os.environ, {"TESTGEN_WORKSPACE_SECRET": "x" * 32}, clear=False):
            owner, token = issue_workspace()
            self.assertEqual(verify_workspace(token), owner)
            self.assertIsNone(verify_workspace(token + "x"))

    def test_short_secret_is_not_accepted(self):
        with patch.dict(os.environ, {"TESTGEN_WORKSPACE_SECRET": "too-short"}, clear=False):
            with self.assertRaises(RuntimeError):
                issue_workspace()


if __name__ == "__main__":
    unittest.main()
