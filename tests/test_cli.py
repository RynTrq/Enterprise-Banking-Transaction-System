from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from banking.cli import main  # noqa: E402


class CliTests(unittest.TestCase):
    def test_cli_create_account_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "bank.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store",
                        str(store),
                        "--json",
                        "create-account",
                        "Ada Lovelace",
                        "--opening-balance",
                        "10",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["owner_name"], "Ada Lovelace")
            self.assertEqual(payload["balance"], "10.00")

    def test_cli_reports_domain_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "--store",
                        str(Path(directory) / "bank.json"),
                        "create-account",
                        "A",
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("Owner name", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
