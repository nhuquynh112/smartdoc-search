"""Prevent mutation tests from using a developer's demo database."""
import os
import re
import unittest

from psycopg.conninfo import conninfo_to_dict

from smartdoc.config import database_url


def require_disposable_database():
    expected = os.environ.get("SMARTDOC_ISOLATED_TEST_DB", "")
    if not re.fullmatch(r"smartdoc_tv3_test_[0-9a-f]{32}", expected):
        raise unittest.SkipTest("Run via python -m scripts.test_tv3_isolated_database --all-tests.")
    if conninfo_to_dict(database_url()).get("dbname") != expected:
        raise RuntimeError("Mutation test database does not match the isolated runner target.")


class DisposableDatabaseTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        require_disposable_database()
