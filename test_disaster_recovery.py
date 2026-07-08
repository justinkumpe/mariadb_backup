#!/usr/bin/env python3

"""Unit tests for disaster recovery helpers."""

import configparser
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mariadb_manager import MariaDBManager


class DisasterRecoveryHelperTests(unittest.TestCase):
    def setUp(self):
        self.test_config = tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False)
        self.test_config.write(
            "[mysql]\nhost = localhost\nuser = restore_admin\npassword = test\nport = 3306\n"
        )
        self.test_config.close()
        self.manager = MariaDBManager(self.test_config.name)

    def tearDown(self):
        os.remove(self.test_config.name)

    def test_sql_escape_string(self):
        self.assertEqual(self.manager._sql_escape_string("plain"), "plain")
        self.assertEqual(self.manager._sql_escape_string("a'b"), "a''b")
        self.assertEqual(self.manager._sql_escape_string("a\\b"), "a\\\\b")

    def test_parse_datadir_from_cnf(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cnf", delete=False) as handle:
            handle.write(
                "[mysqld]\n"
                "datadir = /custom/mysql/data\n"
            )
            path = handle.name

        try:
            self.assertEqual(
                self.manager._parse_datadir_from_cnf(path),
                "/custom/mysql/data",
            )
        finally:
            os.remove(path)

    def test_detect_datadir_from_cnf_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cnf_path = os.path.join(tmpdir, "50-server.cnf")
            with open(cnf_path, "w") as handle:
                handle.write("[mysqld]\n")
                handle.write(f"datadir = {tmpdir}/mariadb-data\n")

            with patch.object(self.manager, "_detect_datadir", wraps=self.manager._detect_datadir):
                with patch("shutil.which", return_value=None):
                    parser = configparser.ConfigParser()
                    parser.read(cnf_path)
                    self.assertEqual(
                        self.manager._parse_datadir_from_cnf(cnf_path),
                        f"{tmpdir}/mariadb-data",
                    )

    def test_reset_requires_root(self):
        with patch.object(self.manager, "_is_effective_root", return_value=False):
            self.assertFalse(self.manager._reset_mysql_system_tables("/var/lib/mysql"))

    @patch.object(MariaDBManager, "test_connection", return_value=True)
    @patch.object(MariaDBManager, "_can_connect_root_socket", return_value=True)
    @patch.object(MariaDBManager, "_diagnose_mariadb")
    @patch.object(MariaDBManager, "_update_config_mysql_credentials", return_value=True)
    @patch.object(MariaDBManager, "_configure_restore_access", return_value=True)
    def test_disaster_recovery_configures_access_when_healthy(
        self,
        mock_configure,
        mock_update_config,
        mock_diagnose,
        mock_root_socket,
        mock_test_connection,
    ):
        mock_diagnose.return_value = {
            "service": "mariadb",
            "service_running": True,
            "service_active": "active",
            "datadir": "/var/lib/mysql",
            "mysql_system_dir": "/var/lib/mysql/mysql",
            "mysql_system_dir_exists": True,
            "connection_ok": True,
            "root_socket_ok": True,
            "journal_tail": "",
        }

        result = self.manager.disaster_recovery(
            admin_user="restore_admin",
            admin_password="secret-pass",
            skip_confirm=True,
        )

        self.assertTrue(result)
        mock_configure.assert_called_once()
        mock_update_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
