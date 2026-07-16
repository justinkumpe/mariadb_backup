#!/usr/bin/env python3

"""Unit tests for disaster recovery helpers."""

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
            "[mysql]\nhost = localhost\nuser = backup_manager\npassword = config-secret\nport = 3306\n"
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
            with open(cnf_path, "w", encoding="utf-8") as handle:
                handle.write("[mysqld]\n")
                handle.write(f"datadir = {tmpdir}/mariadb-data\n")

            self.assertEqual(
                self.manager._parse_datadir_from_cnf(cnf_path),
                f"{tmpdir}/mariadb-data",
            )

    def test_reset_requires_root(self):
        with patch.object(self.manager, "_is_effective_root", return_value=False):
            self.assertFalse(self.manager._reset_mysql_system_tables("/var/lib/mysql"))

    @patch.object(MariaDBManager, "_probe_connection", return_value=True)
    @patch.object(MariaDBManager, "_can_connect_root_socket", return_value=True)
    @patch.object(MariaDBManager, "_diagnose_mariadb")
    @patch.object(MariaDBManager, "_update_config_mysql_credentials", return_value=True)
    @patch.object(MariaDBManager, "_configure_restore_access", return_value=True)
    def test_disaster_recovery_uses_config_password(
        self,
        mock_configure,
        mock_update_config,
        mock_diagnose,
        _mock_root_socket,
        _mock_probe,
    ):
        mock_diagnose.return_value = {
            "service": "mariadb",
            "service_running": True,
            "service_active": "active",
            "datadir": "/var/lib/mysql",
            "mysql_system_dir": "/var/lib/mysql/mysql",
            "mysql_system_dir_exists": True,
            "socket_path": "/run/mysqld/mysqld.sock",
            "connection_ok": True,
            "root_socket_ok": True,
            "journal_tail": "",
        }

        result = self.manager.disaster_recovery(skip_confirm=True)

        self.assertTrue(result)
        mock_configure.assert_called_once()
        args, _kwargs = mock_configure.call_args
        self.assertEqual(args[0], "backup_manager")
        self.assertEqual(args[1], "config-secret")
        mock_update_config.assert_called_once()

    @patch.object(MariaDBManager, "_is_effective_root", return_value=True)
    @patch.object(MariaDBManager, "_start_mariadb_service", return_value=False)
    @patch.object(MariaDBManager, "_reset_mysql_system_tables", return_value=True)
    @patch.object(MariaDBManager, "_probe_connection", return_value=True)
    @patch.object(MariaDBManager, "_configure_restore_access", return_value=True)
    @patch.object(MariaDBManager, "_update_config_mysql_credentials", return_value=True)
    @patch.object(MariaDBManager, "_diagnose_mariadb")
    def test_disaster_recovery_auto_resets_when_down(
        self,
        mock_diagnose,
        _mock_update,
        mock_configure,
        _mock_probe,
        mock_reset,
        mock_start,
        _mock_root,
    ):
        unhealthy = {
            "service": "mariadb",
            "service_running": False,
            "service_active": "failed",
            "datadir": "/var/lib/mysql",
            "mysql_system_dir": "/var/lib/mysql/mysql",
            "mysql_system_dir_exists": True,
            "socket_path": None,
            "connection_ok": False,
            "root_socket_ok": False,
            "journal_tail": "InnoDB: corruption",
        }
        healthy = {
            "service": "mariadb",
            "service_running": True,
            "service_active": "active",
            "datadir": "/var/lib/mysql",
            "mysql_system_dir": "/var/lib/mysql/mysql",
            "mysql_system_dir_exists": True,
            "socket_path": "/run/mysqld/mysqld.sock",
            "connection_ok": False,
            "root_socket_ok": True,
            "journal_tail": "",
        }
        mock_diagnose.side_effect = [unhealthy, healthy]

        result = self.manager.disaster_recovery(skip_confirm=True)

        self.assertTrue(result)
        mock_start.assert_called()
        mock_reset.assert_called_once()
        mock_configure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
