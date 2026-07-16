#!/usr/bin/env python3

"""
MariaDB Backup and Restore Manager
Comprehensive solution for backing up and restoring MariaDB databases
with support for master/slave replication configuration.
"""

import argparse
import configparser
import datetime
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


class MariaDBManager:
    SYSTEM_SCHEMAS = {"mysql", "information_schema", "performance_schema", "sys"}
    RESTORE_MODES = {"full", "users-grants", "databases", "schema", "data"}

    def __init__(self, config_file=None):
        # If no config specified, search for existing configs
        if config_file is None:
            config_file = self.find_config_file()
        
        self.config_file = config_file
        self.config = self.load_config()
    
    def find_config_file(self):
        """Find existing config file or determine where to create one"""
        # Priority order for searching/creating config files
        search_locations = [
            '/etc/mariadb_backup.conf',
            os.path.expanduser('~/.config/mariadb_backup.conf'),
            'mariadb_backup.conf',  # Current directory (last resort)
        ]
        
        # Check if any exist
        existing = []
        for loc in search_locations:
            if os.path.exists(loc):
                existing.append(loc)
        
        if len(existing) == 0:
            # No config exists, use first writable location
            for loc in search_locations:
                try:
                    # Try to create parent directory
                    parent = os.path.dirname(loc)
                    if parent and not os.path.exists(parent):
                        os.makedirs(parent, exist_ok=True)
                    # Test if we can write there
                    test_file = loc + '.test'
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    return loc
                except (PermissionError, OSError):
                    continue
            # Fallback to current directory
            return 'mariadb_backup.conf'
        
        elif len(existing) == 1:
            # One config found, use it
            return existing[0]
        
        else:
            # Multiple configs found - warn and use first one
            print(f"\n⚠️  WARNING: Multiple config files found:")
            for idx, loc in enumerate(existing, 1):
                size = os.path.getsize(loc)
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(loc))
                print(f"  {idx}. {loc}")
                print(f"     Size: {size} bytes, Modified: {mtime}")
            
            print(f"\nUsing: {existing[0]}")
            print(f"To use a different config, run with: --config <path>")
            print(f"Or delete unused config files.\n")
            
            return existing[0]

    def load_config(self):
        """Load configuration from file or create default"""
        config = configparser.ConfigParser()

        if os.path.exists(self.config_file):
            config.read(self.config_file)
            
            # Ensure all required sections exist
            if not config.has_section('mysql'):
                config.add_section('mysql')
            if not config.has_section('backup_paths'):
                config.add_section('backup_paths')
            if not config.has_section('options'):
                config.add_section('options')
            
            # Set defaults for missing values
            if not config.has_option('mysql', 'host'):
                config.set('mysql', 'host', 'localhost')
            if not config.has_option('mysql', 'user'):
                config.set('mysql', 'user', 'root')
            if not config.has_option('mysql', 'password'):
                config.set('mysql', 'password', '')
            if not config.has_option('mysql', 'port'):
                config.set('mysql', 'port', '3306')
            
            # Set rotation defaults if missing
            if not config.has_section('rotation'):
                config.add_section('rotation')
            if not config.has_option('rotation', 'hourly_keep'):
                config.set('rotation', 'hourly_keep', '24')
            if not config.has_option('rotation', 'daily_keep'):
                config.set('rotation', 'daily_keep', '31')
            if not config.has_option('rotation', 'monthly_keep'):
                config.set('rotation', 'monthly_keep', '12')

            # Replication defaults
            if not config.has_section('replication'):
                config.add_section('replication')
            if not config.has_option('replication', 'master_host'):
                config.set('replication', 'master_host', '')
            if not config.has_option('replication', 'master_user'):
                config.set('replication', 'master_user', '')
            if not config.has_option('replication', 'master_password'):
                config.set('replication', 'master_password', '')
            if not config.has_option('replication', 'master_port'):
                config.set('replication', 'master_port', '3306')

            # Webhook defaults
            if not config.has_section('webhooks'):
                config.add_section('webhooks')
            if not config.has_option('webhooks', 'success_url'):
                config.set('webhooks', 'success_url', '')
            if not config.has_option('webhooks', 'failure_url'):
                config.set('webhooks', 'failure_url', '')
                
        else:
            # Create default configuration
            config.add_section('mysql')
            config.set('mysql', 'host', 'localhost')
            config.set('mysql', 'user', 'root')
            config.set('mysql', 'password', '')
            config.set('mysql', 'port', '3306')
            
            config.add_section('backup_paths')
            config.set('backup_paths', 'hourly', '/var/backups/mariadb/hourly')
            config.set('backup_paths', 'daily', '/var/backups/mariadb/daily')
            config.set('backup_paths', 'monthly', '/var/backups/mariadb/monthly')
            
            config.add_section('options')
            config.set('options', 'compression', 'yes')
            config.set('options', 'encryption', 'no')
            config.set('options', 'encryption_key_file', '/root/.mariadb_backup_key')
            
            config.add_section('rotation')
            config.set('rotation', 'hourly_keep', '24')
            config.set('rotation', 'daily_keep', '31')
            config.set('rotation', 'monthly_keep', '12')

            config.add_section('replication')
            config.set('replication', 'master_host', '')
            config.set('replication', 'master_user', '')
            config.set('replication', 'master_password', '')
            config.set('replication', 'master_port', '3306')

            config.add_section('webhooks')
            config.set('webhooks', 'success_url', '')
            config.set('webhooks', 'failure_url', '')

            self.save_config(config)
            print(f"Default configuration created at {self.config_file}")
            print("Please edit the configuration file with your MySQL credentials.")

        return config

    def save_config(self, config=None):
        """Save configuration to file"""
        if config is None:
            config = self.config

        # Get absolute path
        abs_path = os.path.abspath(self.config_file)
        
        # Debug output
        print(f"\n  [DEBUG] save_config() called")
        print(f"  [DEBUG] Target file: {abs_path}")
        print(f"  [DEBUG] File exists before write: {os.path.exists(abs_path)}")
        print(f"  [DEBUG] Sections to save: {config.sections()}")
        
        # Show what we're about to save
        print(f"  [DEBUG] Values being saved:")
        for section in config.sections():
            print(f"    [{section}]")
            for key, value in config.items(section):
                if key == 'password':
                    print(f"      {key} = {'*' * len(value) if value else '(empty)'}")
                else:
                    print(f"      {key} = {value}")
        
        try:
            # Write the file
            with open(abs_path, "w") as f:
                config.write(f)
            print(f"  [DEBUG] File write completed")
            
            # Set permissions
            os.chmod(abs_path, 0o600)
            print(f"  [DEBUG] Permissions set to 600")
            
            # Verify file was written
            if os.path.exists(abs_path):
                size = os.path.getsize(abs_path)
                print(f"  [DEBUG] File verified: {size} bytes")
                
                # Read back first few lines to verify content
                print(f"  [DEBUG] Reading back file contents:")
                with open(abs_path, 'r') as f:
                    lines = f.readlines()[:10]  # First 10 lines
                    for line in lines:
                        print(f"    {line.rstrip()}")
                
                # Try to parse it back
                test_config = configparser.ConfigParser()
                test_config.read(abs_path)
                print(f"  [DEBUG] Parse verification: {len(test_config.sections())} sections")
                
                if test_config.has_section('mysql'):
                    saved_host = test_config.get('mysql', 'host')
                    print(f"  [DEBUG] Verified mysql.host = {saved_host}")
                
                return True
            else:
                print(f"  [DEBUG] ERROR: File does not exist after write!")
                return False
                
        except Exception as e:
            print(f"  [DEBUG] EXCEPTION during save: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_mysql_connection_args(self, host_override=None):
        """Get MySQL connection arguments
        
        Args:
            host_override: If provided, use this host instead of config host
        """
        args = []
        
        # Use override if provided, otherwise use config
        host = host_override if host_override else self.config['mysql']['host']
        
        # Don't pass host parameter for localhost to use Unix socket connection
        # This avoids IPv6 issues where localhost might resolve to ::1
        if host.lower() != 'localhost':
            args.append(f"--host={host}")
            # Only add port when using TCP/IP connection (not Unix socket)
            args.append(f"--port={self.config['mysql']['port']}")
        
        args.extend([
            f"--user={self.config['mysql']['user']}",
            f"--password={self.config['mysql']['password']}",
            "--max-allowed-packet=1G",
        ])
        
        return args

    def _format_restore_error(self, stderr):
        """Format restore errors to avoid printing huge SQL statements"""
        if not stderr:
            return "Unknown MySQL error"

        cleaned = stderr.strip()
        packet_hint = ""
        if "max_allowed_packet" in cleaned.lower() or "packet bigger than" in cleaned.lower():
            packet_hint = "\nHint: Increase server max_allowed_packet in MariaDB config and retry restore."

        if len(cleaned) <= 2000:
            return f"{cleaned}{packet_hint}"

        head = cleaned[:800]
        tail = cleaned[-800:]
        return (
            f"{head}\n... [error output truncated] ...\n{tail}"
            f"\nHint: Restore failed while replaying a very large statement."
            f" Verify MariaDB server max_allowed_packet is high enough (for example 256M-1G).{packet_hint}"
        )

    def _get_server_packet_sizes(self):
        """Get global/session max_allowed_packet values in bytes."""
        cmd = (
            ["mysql"]
            + self.get_mysql_connection_args()
            + ["-N", "-B", "-e", "SELECT @@global.max_allowed_packet, @@session.max_allowed_packet;"]
        )
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if result.returncode != 0 or not result.stdout.strip():
            return None, None

        parts = result.stdout.strip().split("\t")
        if len(parts) < 2:
            return None, None

        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None, None

    def _try_raise_global_packet_size(self, target_bytes=1073741824):
        """Best-effort attempt to raise global max_allowed_packet."""
        cmd = (
            ["mysql"]
            + self.get_mysql_connection_args()
            + ["-e", f"SET GLOBAL max_allowed_packet={target_bytes};"]
        )
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return result.returncode == 0

    def _run_mysql_sql(self, sql):
        """Run a SQL statement and return (returncode, stdout, stderr)."""
        cmd = ["mysql"] + self.get_mysql_connection_args() + ["-N", "-B", "-e", sql]
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()

    def _get_global_variable(self, var_name):
        """Get global server variable value as string, or None on failure."""
        code, stdout, _ = self._run_mysql_sql(f"SELECT @@GLOBAL.{var_name};")
        if code != 0 or not stdout:
            return None
        return stdout.splitlines()[0].strip()

    def _set_global_variable(self, var_name, value):
        """Set global server variable and return (success, error)."""
        code, _, stderr = self._run_mysql_sql(f"SET GLOBAL {var_name}={value};")
        return code == 0, stderr

    def _normalize_toggle(self, value, default="OFF"):
        """Normalize MariaDB boolean-like values to ON/OFF."""
        if value is None:
            return default

        normalized = str(value).strip().lower()
        if normalized in {"1", "on", "true", "yes"}:
            return "ON"
        if normalized in {"0", "off", "false", "no"}:
            return "OFF"
        return default

    def _enable_protected_restore(self):
        """Enable restore protections and return previous state snapshot."""
        state = {
            "read_only": self._get_global_variable("read_only"),
            "event_scheduler": self._get_global_variable("event_scheduler"),
            "offline_mode": self._get_global_variable("offline_mode"),
        }

        ok, err = self._set_global_variable("read_only", "ON")
        if not ok:
            return False, state, f"Failed to set read_only=ON: {err or 'unknown error'}"

        print(
            "INFO: Protected restore uses read_only/event_scheduler/offline_mode where available. "
            "Privileged users may still write during restore on some MariaDB setups."
        )

        # Stop events from mutating data during restore.
        ok, err = self._set_global_variable("event_scheduler", "OFF")
        if not ok:
            print(
                f"WARNING: Could not set event_scheduler=OFF: {err or 'unknown error'}"
            )

        # Best effort: where available, offline_mode blocks normal client logins.
        if state["offline_mode"] is not None:
            ok, err = self._set_global_variable("offline_mode", "ON")
            if not ok:
                print(
                    f"WARNING: Could not set offline_mode=ON: {err or 'unknown error'}"
                )

        return True, state, None

    def _disable_protected_restore(self, previous_state):
        """Restore global settings captured before protected restore."""
        if not previous_state:
            return

        # Restore scheduler/login controls first, then read-only protections.
        old_event = previous_state.get("event_scheduler")
        if old_event is not None:
            desired = self._normalize_toggle(old_event, default="ON")
            ok, err = self._set_global_variable("event_scheduler", desired)
            if not ok:
                print(
                    f"WARNING: Failed to restore event_scheduler={desired}: {err or 'unknown error'}"
                )

        old_offline = previous_state.get("offline_mode")
        if old_offline is not None:
            desired = self._normalize_toggle(old_offline, default="OFF")
            ok, err = self._set_global_variable("offline_mode", desired)
            if not ok:
                print(
                    f"WARNING: Failed to restore offline_mode={desired}: {err or 'unknown error'}"
                )

        old_read = previous_state.get("read_only")
        if old_read is not None:
            desired = self._normalize_toggle(old_read, default="OFF")
            ok, err = self._set_global_variable("read_only", desired)
            if not ok:
                print(
                    f"WARNING: Failed to restore read_only={desired}: {err or 'unknown error'}"
                )

    def _mysql_client_bin(self):
        """Prefer mariadb client when available, fall back to mysql."""
        for cmd in ("mariadb", "mysql"):
            if shutil.which(cmd):
                return cmd
        return "mysql"

    def _detect_mariadb_service_name(self):
        """Detect MariaDB/MySQL service name even when the unit is failed/inactive."""
        if not shutil.which("systemctl"):
            return None

        candidates = ["mariadb", "mysql"]
        for service in candidates:
            # is-active returns 0 only when active; still useful for identity.
            _, active_out, _ = self._run_systemctl("is-active", service)
            if active_out in {"active", "activating", "reloading"}:
                return service

            # Unit exists when is-enabled returns enabled/disabled/static/etc (not "not-found").
            _, enabled_out, _ = self._run_systemctl("is-enabled", service)
            if enabled_out and enabled_out not in {"not-found", "unknown"}:
                return service

            # Fallback: status exit 0 (active) or 3 (inactive/dead) means unit exists.
            status = subprocess.run(
                ["systemctl", "status", service],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
            )
            if status.returncode in {0, 3}:
                return service
            # Failed units often return 1/4 but still exist.
            combined = f"{status.stdout or ''}\n{status.stderr or ''}".lower()
            if f"{service}.service" in combined or "loaded:" in combined:
                return service

        return None

    def _restart_mariadb_service(self):
        """Best-effort restart of MariaDB service to clear transient global state."""
        if not shutil.which("systemctl"):
            print("WARNING: systemctl not found; skipping MariaDB restart")
            return False

        service = self._detect_mariadb_service_name()
        if not service:
            print("WARNING: Could not detect MariaDB/MySQL systemd service; skipping restart")
            return False

        print(f"Restarting service '{service}' to ensure clean post-restore state...")
        ok, _, stderr = self._run_systemctl("restart", service)
        if not ok:
            print(
                f"WARNING: Failed to restart {service}: {stderr or 'unknown error'}"
            )
            return False

        print(f"✓ Service '{service}' restarted")
        return True

    def _is_effective_root(self):
        """Return True when running with privileges needed for service/datadir operations."""
        return hasattr(os, "geteuid") and os.geteuid() == 0

    def _run_systemctl(self, action, service):
        """Run a systemctl action and return (success, stdout, stderr)."""
        if not shutil.which("systemctl"):
            return False, "", "systemctl not found"
        cmd = ["systemctl", action, service]
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return result.returncode == 0, (result.stdout or "").strip(), (result.stderr or "").strip()

    def _get_mariadb_service_status(self):
        """Return systemd status details for MariaDB/MySQL, or None if unavailable."""
        service = self._detect_mariadb_service_name()
        if not service:
            return None

        _, active_out, _ = self._run_systemctl("is-active", service)
        _, enabled_out, _ = self._run_systemctl("is-enabled", service)
        active_out = active_out or "unknown"
        enabled_out = enabled_out or "unknown"
        return {
            "service": service,
            "active": active_out,
            "enabled": enabled_out,
            "running": active_out == "active",
        }

    def _get_service_journal_tail(self, service, lines=30):
        """Return recent journal lines for a systemd service."""
        if not shutil.which("journalctl"):
            return ""
        cmd = ["journalctl", "-u", service, "-n", str(lines), "--no-pager"]
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            return result.stderr.strip() if result.stderr else ""
        return result.stdout.strip()

    def _stop_mariadb_service(self):
        """Stop MariaDB/MySQL systemd service. Already-stopped is success."""
        service = self._detect_mariadb_service_name()
        if not service:
            print("ERROR: Could not detect MariaDB/MySQL systemd service")
            return False

        status = self._get_mariadb_service_status()
        if status and not status["running"] and status["active"] in {"inactive", "dead", "failed"}:
            print(f"Service '{service}' already stopped ({status['active']})")
            # Clear failed state so a later start can succeed.
            self._run_systemctl("reset-failed", service)
            return True

        print(f"Stopping service '{service}'...")
        ok, _, stderr = self._run_systemctl("stop", service)
        if not ok:
            # Treat already inactive as success.
            _, active_out, _ = self._run_systemctl("is-active", service)
            if active_out in {"inactive", "dead", "failed"}:
                self._run_systemctl("reset-failed", service)
                print(f"✓ Service '{service}' is stopped")
                return True
            print(f"ERROR: Failed to stop {service}: {stderr or 'unknown error'}")
            return False

        print(f"✓ Service '{service}' stopped")
        return True

    def _start_mariadb_service(self, wait_seconds=30):
        """Start MariaDB/MySQL systemd service and wait for readiness."""
        service = self._detect_mariadb_service_name()
        if not service:
            print("ERROR: Could not detect MariaDB/MySQL systemd service")
            return False

        self._run_systemctl("reset-failed", service)
        print(f"Starting service '{service}'...")
        ok, _, stderr = self._run_systemctl("start", service)
        if not ok:
            print(f"ERROR: Failed to start {service}: {stderr or 'unknown error'}")
            journal = self._get_service_journal_tail(service, lines=40)
            if journal:
                print("Recent service log:")
                print(journal[-3000:])
            return False

        ping_bins = []
        if shutil.which("mariadb-admin"):
            ping_bins.append("mariadb-admin")
        if shutil.which("mysqladmin"):
            ping_bins.append("mysqladmin")

        if ping_bins:
            for _ in range(wait_seconds):
                for ping_bin in ping_bins:
                    ping = subprocess.run(
                        [ping_bin, "ping", "--silent"],
                        capture_output=True,
                        text=True,
                        stdin=subprocess.DEVNULL,
                    )
                    if ping.returncode == 0:
                        print(f"✓ Service '{service}' is ready")
                        return True
                # Also accept a successful SELECT via socket once the sock appears.
                if self._probe_connection(quiet=True) or self._can_connect_root_socket():
                    print(f"✓ Service '{service}' is ready")
                    return True
                time.sleep(1)
            print(
                f"WARNING: Service '{service}' started but readiness check did not succeed "
                f"within {wait_seconds} seconds"
            )
            return False

        # No admin ping tool; fall back to client probe.
        for _ in range(wait_seconds):
            if self._probe_connection(quiet=True) or self._can_connect_root_socket():
                print(f"✓ Service '{service}' is ready")
                return True
            time.sleep(1)

        print(f"WARNING: Service '{service}' start command completed; readiness uncertain")
        return True

    def _parse_datadir_from_cnf(self, path):
        """Parse datadir from a MariaDB/MySQL config file."""
        parser = configparser.ConfigParser()
        try:
            # MariaDB cnf files may lack section headers; tolerate that.
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
            if not re.search(r"^\s*\[[^\]]+\]", content, flags=re.M):
                content = "[mysqld]\n" + content
            parser.read_string(content)
        except (configparser.Error, OSError):
            return None

        for section in parser.sections():
            if parser.has_option(section, "datadir"):
                value = parser.get(section, "datadir").strip()
                if value:
                    return value
        return None

    def _detect_datadir(self):
        """Best-effort detection of MariaDB datadir path."""
        for cmd_name in ("mysqld", "mariadbd"):
            if not shutil.which(cmd_name):
                continue
            try:
                result = subprocess.run(
                    [cmd_name, "--verbose", "--help"],
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            for line in (result.stdout + result.stderr).splitlines():
                stripped = line.strip()
                if stripped.startswith("datadir"):
                    parts = stripped.split(None, 1)
                    if len(parts) == 2 and parts[1]:
                        return parts[1].strip()

        cnf_paths = [
            "/etc/mysql/mariadb.conf.d/50-server.cnf",
            "/etc/mysql/my.cnf",
            "/etc/my.cnf",
        ]
        for path in cnf_paths:
            if os.path.exists(path):
                datadir = self._parse_datadir_from_cnf(path)
                if datadir:
                    return datadir

        return "/var/lib/mysql"

    def _find_install_db_command(self):
        """Locate mariadb-install-db or mysql_install_db."""
        for cmd in ("mariadb-install-db", "mysql_install_db"):
            if shutil.which(cmd):
                return cmd
        return None

    def _find_server_bin(self):
        """Locate mysqld/mariadbd binary for bootstrap recovery."""
        for cmd in ("mariadbd", "mysqld"):
            if shutil.which(cmd):
                return cmd
        return None

    def _get_mysql_unix_account(self):
        """Return (user, group) for datadir ownership, defaulting to mysql."""
        try:
            import pwd

            entry = pwd.getpwnam("mysql")
            return entry.pw_name, entry.pw_name
        except (ImportError, KeyError):
            return "mysql", "mysql"

    def _sql_escape_string(self, value):
        """Escape a value for use inside single-quoted SQL string literals."""
        return value.replace("\\", "\\\\").replace("'", "''")

    def _find_mysql_socket(self):
        """Return first existing MySQL/MariaDB unix socket path."""
        socket_locations = [
            "/run/mysqld/mysqld.sock",
            "/var/run/mysqld/mysqld.sock",
            "/var/lib/mysql/mysql.sock",
            "/tmp/mysql.sock",
            "/run/mysql/mysql.sock",
        ]
        for sock in socket_locations:
            if os.path.exists(sock):
                return sock
        return None

    def _run_mysql_cli(self, sql, user="root", password=None, socket_path=None, use_config_creds=False):
        """Run SQL via mysql/mariadb client. Returns (ok, stdout, stderr)."""
        client = self._mysql_client_bin()
        cmd = [client, "--no-defaults", "-N", "-B", "-e", sql]
        env = os.environ.copy()

        if use_config_creds:
            cmd.extend(self.get_mysql_connection_args())
            password = self.config["mysql"].get("password", "")
        else:
            cmd.append(f"--user={user}")
            if socket_path:
                cmd.append(f"--socket={socket_path}")
            elif self.config["mysql"].get("host", "localhost").lower() != "localhost":
                cmd.append(f"--host={self.config['mysql']['host']}")
                cmd.append(f"--port={self.config['mysql']['port']}")

        cmd_without_pwd = [arg for arg in cmd if not arg.startswith("--password=")]
        if password:
            env["MYSQL_PWD"] = password

        result = subprocess.run(
            cmd_without_pwd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=env,
            timeout=20,
        )
        return result.returncode == 0, (result.stdout or "").strip(), (result.stderr or "").strip()

    def _run_mysql_root_socket(self, sql):
        """Run SQL as local root via Unix socket (no config password)."""
        socket_path = self._find_mysql_socket()
        return self._run_mysql_cli(sql, user="root", password=None, socket_path=socket_path)

    def _can_connect_root_socket(self):
        """Return True when OS root can connect to MariaDB via local socket."""
        ok, _, _ = self._run_mysql_root_socket("SELECT 1;")
        return ok

    def _probe_connection(self, quiet=True):
        """Quiet connection probe using config credentials."""
        try:
            ok, _, stderr = self._run_mysql_cli("SELECT 1;", use_config_creds=True)
            if not quiet and not ok and stderr:
                password = self.config["mysql"].get("password", "")
                if password:
                    stderr = stderr.replace(password, "***")
                print(f"Connection probe failed: {stderr}")
            return ok
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _diagnose_mariadb(self):
        """Collect MariaDB health details for disaster recovery decisions."""
        status = self._get_mariadb_service_status()
        datadir = self._detect_datadir()
        mysql_dir = os.path.join(datadir, "mysql") if datadir else None
        socket_path = self._find_mysql_socket()

        diagnosis = {
            "service": status["service"] if status else None,
            "service_running": bool(status and status["running"]),
            "service_active": status["active"] if status else "unknown",
            "datadir": datadir,
            "mysql_system_dir": mysql_dir,
            "mysql_system_dir_exists": bool(mysql_dir and os.path.isdir(mysql_dir)),
            "socket_path": socket_path,
            "connection_ok": self._probe_connection(quiet=True),
            "root_socket_ok": self._can_connect_root_socket() if self._is_effective_root() else False,
            "journal_tail": "",
        }

        if status and status["service"]:
            diagnosis["journal_tail"] = self._get_service_journal_tail(status["service"])

        return diagnosis

    def _backup_mysql_system_tables(self, datadir):
        """Backup mysql system schema directory before destructive recovery."""
        mysql_dir = os.path.join(datadir, "mysql")
        if not os.path.isdir(mysql_dir):
            print(f"WARNING: mysql system directory not found at {mysql_dir}; skipping backup")
            return None

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(datadir, f"mysql_system_backup_{timestamp}")
        print(f"Backing up {mysql_dir} -> {backup_dir}")
        shutil.copytree(mysql_dir, backup_dir)
        print(f"✓ mysql system tables backed up to {backup_dir}")
        return backup_dir

    def _remove_mysql_system_table_files(self, datadir):
        """Remove mysql system schema files while preserving application databases."""
        mysql_dir = os.path.join(datadir, "mysql")
        if os.path.isdir(mysql_dir):
            print(f"Removing corrupted mysql system files in {mysql_dir}")
            shutil.rmtree(mysql_dir)

        os.makedirs(mysql_dir, exist_ok=True)
        user, group = self._get_mysql_unix_account()
        try:
            shutil.chown(mysql_dir, user, group)
        except (LookupError, PermissionError, OSError) as exc:
            print(f"WARNING: Could not chown {mysql_dir} to {user}:{group}: {exc}")

        print(f"✓ mysql system directory reset at {mysql_dir}")
        return True

    def _run_install_db(self, datadir):
        """Reinitialize MariaDB system tables in an existing datadir."""
        install_cmd = self._find_install_db_command()
        if not install_cmd:
            print("ERROR: mariadb-install-db/mysql_install_db not found")
            return False

        user, _ = self._get_mysql_unix_account()
        cmd = [install_cmd, f"--user={user}", f"--datadir={datadir}"]
        print(f"Running {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            output = (result.stderr or result.stdout or "").strip()
            print(f"ERROR: {install_cmd} failed: {output or 'unknown error'}")
            return False

        print(f"✓ {install_cmd} completed successfully")
        return True

    def _configure_restore_access(self, admin_user, admin_password, admin_host="localhost", root_password=None):
        """Create or update restore admin credentials using local root socket access."""
        user_esc = self._sql_escape_string(admin_user)
        host_esc = self._sql_escape_string(admin_host)
        pass_esc = self._sql_escape_string(admin_password)

        statements = [
            f"CREATE USER IF NOT EXISTS '{user_esc}'@'{host_esc}' IDENTIFIED BY '{pass_esc}';",
            f"ALTER USER '{user_esc}'@'{host_esc}' IDENTIFIED BY '{pass_esc}';",
            f"GRANT ALL PRIVILEGES ON *.* TO '{user_esc}'@'{host_esc}' WITH GRANT OPTION;",
            "FLUSH PRIVILEGES;",
        ]

        if root_password:
            root_esc = self._sql_escape_string(root_password)
            statements.insert(
                0,
                f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_esc}';",
            )

        sql = "\n".join(statements)
        ok, _, stderr = self._run_mysql_root_socket(sql)
        if not ok:
            print(f"ERROR: Failed to configure restore access: {stderr or 'unknown error'}")
            return False

        print(f"✓ Restore user '{admin_user}'@'{admin_host}' configured")
        return True

    def _wait_for_socket(self, timeout_seconds=30):
        """Wait for unix socket to appear."""
        for _ in range(timeout_seconds):
            sock = self._find_mysql_socket()
            if sock:
                return sock
            time.sleep(1)
        return None

    def _bootstrap_with_skip_grant_tables(self, admin_user, admin_password, admin_host="localhost", root_password=None):
        """Start temporary mysqld with --skip-grant-tables to repair credentials."""
        if not self._is_effective_root():
            print("ERROR: skip-grant-tables recovery requires root privileges (use sudo).")
            return False

        server_bin = self._find_server_bin()
        if not server_bin:
            print("ERROR: mysqld/mariadbd not found for skip-grant-tables recovery")
            return False

        datadir = self._detect_datadir()
        user, _ = self._get_mysql_unix_account()

        print("Attempting skip-grant-tables bootstrap to restore admin access...")
        if not self._stop_mariadb_service():
            return False

        cmd = [
            server_bin,
            f"--user={user}",
            f"--datadir={datadir}",
            "--skip-grant-tables",
            "--skip-networking",
            "--socket=/tmp/mariadb_dr.sock",
        ]
        print(f"Starting temporary server: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            sock = None
            for _ in range(30):
                if os.path.exists("/tmp/mariadb_dr.sock"):
                    sock = "/tmp/mariadb_dr.sock"
                    break
                if proc.poll() is not None:
                    err = (proc.stderr.read() if proc.stderr else "") or ""
                    print(f"ERROR: Temporary server exited early: {err[-2000:]}")
                    return False
                time.sleep(1)

            if not sock:
                print("ERROR: Temporary skip-grant-tables socket did not appear")
                return False

            # With skip-grant-tables, FLUSH PRIVILEGES is required before ALTER USER on some versions.
            bootstrap_sql = "FLUSH PRIVILEGES;\n"
            user_esc = self._sql_escape_string(admin_user)
            host_esc = self._sql_escape_string(admin_host)
            pass_esc = self._sql_escape_string(admin_password)
            bootstrap_sql += (
                f"CREATE USER IF NOT EXISTS '{user_esc}'@'{host_esc}' IDENTIFIED BY '{pass_esc}';\n"
                f"ALTER USER '{user_esc}'@'{host_esc}' IDENTIFIED BY '{pass_esc}';\n"
                f"GRANT ALL PRIVILEGES ON *.* TO '{user_esc}'@'{host_esc}' WITH GRANT OPTION;\n"
            )
            if root_password:
                root_esc = self._sql_escape_string(root_password)
                bootstrap_sql += f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_esc}';\n"
            bootstrap_sql += "FLUSH PRIVILEGES;"

            ok, _, stderr = self._run_mysql_cli(
                bootstrap_sql, user="root", password=None, socket_path=sock
            )
            if not ok:
                print(f"ERROR: skip-grant-tables credential repair failed: {stderr or 'unknown error'}")
                return False

            print("✓ Credentials repaired via skip-grant-tables")
            return True
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            if os.path.exists("/tmp/mariadb_dr.sock"):
                try:
                    os.remove("/tmp/mariadb_dr.sock")
                except OSError:
                    pass
            # Bring normal service back up.
            self._start_mariadb_service()

    def _update_config_mysql_credentials(self, user, password, host=None, port=None):
        """Persist MySQL credentials used by restore operations."""
        self.config.set("mysql", "user", user)
        self.config.set("mysql", "password", password)
        if host is not None:
            self.config.set("mysql", "host", host)
        if port is not None:
            self.config.set("mysql", "port", str(port))
        return self.save_config()

    def _reset_mysql_system_tables(self, datadir, backup=True):
        """Stop MariaDB, reset mysql system schema files, and reinitialize system tables."""
        if not self._is_effective_root():
            print("ERROR: Resetting mysql system tables requires root privileges (use sudo).")
            return False

        if backup:
            self._backup_mysql_system_tables(datadir)

        if not self._stop_mariadb_service():
            return False

        if not self._remove_mysql_system_table_files(datadir):
            return False

        if not self._run_install_db(datadir):
            return False

        return self._start_mariadb_service()

    def disaster_recovery(
        self,
        reset_system_tables=False,
        admin_user=None,
        admin_password=None,
        admin_host="localhost",
        root_password=None,
        skip_confirm=False,
        restore_path=None,
        restore_as_slave=False,
        restore_mode="full",
        protected_restore=True,
        drop_non_system_databases=False,
        restart_after_restore=True,
    ):
        """
        Disaster recovery workflow for servers where MariaDB will not start or credentials are broken.

        Steps:
        1. Diagnose service status, logs, datadir, and connectivity (quiet)
        2. Try start service; if still unhealthy, reset mysql system tables / skip-grant-tables
        3. Configure restore admin user (reuse config password when present)
        4. Optionally restore from a backup path
        """
        print(f"\n{'='*60}")
        print("Disaster Recovery Mode")
        print(f"{'='*60}\n")

        if not self._is_effective_root():
            print(
                "WARNING: Not running as root. Service control and mysql system table reset "
                "require sudo/root."
            )

        diagnosis = self._diagnose_mariadb()
        service = diagnosis["service"] or "mariadb/mysql"
        datadir = diagnosis["datadir"]

        print("Diagnosis:")
        print(f"  Service: {service}")
        print(f"  Service running: {'yes' if diagnosis['service_running'] else 'no'} ({diagnosis['service_active']})")
        print(f"  Datadir: {datadir}")
        print(
            f"  mysql system dir: {diagnosis['mysql_system_dir']} "
            f"({'present' if diagnosis['mysql_system_dir_exists'] else 'missing'})"
        )
        print(f"  Socket: {diagnosis.get('socket_path') or 'not found'}")
        print(f"  Config credentials work: {'yes' if diagnosis['connection_ok'] else 'no'}")
        if self._is_effective_root():
            print(f"  Root socket login works: {'yes' if diagnosis['root_socket_ok'] else 'no'}")

        if diagnosis.get("journal_tail") and not diagnosis["service_running"]:
            print("\nRecent service log:")
            print("-" * 60)
            print(diagnosis["journal_tail"][-3000:])
            print("-" * 60)

        admin_user = admin_user or self.config["mysql"].get("user") or "restore_admin"
        admin_host = admin_host or "localhost"
        config_password = self.config["mysql"].get("password", "").strip()

        if not admin_password:
            if config_password:
                admin_password = config_password
                print(
                    f"\nUsing existing config password for restore user "
                    f"'{admin_user}'@'{admin_host}'"
                )
            elif skip_confirm:
                print("ERROR: No password in config; pass --dr-admin-pass for non-interactive mode")
                return False
            else:
                admin_password = getpass.getpass(
                    f"Enter password for restore user '{admin_user}'@'{admin_host}': "
                ).strip()
                if not admin_password:
                    print("ERROR: Restore user password cannot be empty")
                    return False

        # If service is down, try a normal start before destructive recovery.
        if not diagnosis["service_running"] and self._is_effective_root():
            print("\nService is down — attempting normal start first...")
            if self._start_mariadb_service():
                diagnosis = self._diagnose_mariadb()
            else:
                print("Normal start failed; continuing with recovery options")

        unhealthy = (
            not diagnosis["service_running"]
            or (not diagnosis["connection_ok"] and not diagnosis["root_socket_ok"])
        )

        needs_system_reset = bool(reset_system_tables)
        if not needs_system_reset and unhealthy:
            if skip_confirm:
                # Disaster recovery should overcome a dead server automatically.
                needs_system_reset = not diagnosis["service_running"]
            else:
                print(
                    "\nMariaDB is not healthy. You can reset ONLY the mysql system schema files "
                    "(application database directories are preserved)."
                )
                default = "yes" if not diagnosis["service_running"] else "no"
                answer = input(
                    f"Reset mysql system tables? (yes/no) [{default}]: "
                ).strip().lower()
                if not answer:
                    answer = default
                needs_system_reset = answer in {"y", "yes"}

        if needs_system_reset:
            print("\n⚠️  WARNING: This will stop MariaDB and rebuild mysql system tables.")
            print(f"   Datadir: {datadir}")
            print("   Application database directories outside mysql/ are preserved.")
            if not skip_confirm:
                answer = input("\nContinue with mysql system table reset? (yes/no): ").strip().lower()
                if answer != "yes":
                    print("Disaster recovery cancelled.")
                    return False

            if not self._reset_mysql_system_tables(datadir, backup=True):
                print("ERROR: mysql system table reset failed")
                return False

            diagnosis = self._diagnose_mariadb()

        # If server is up but auth is broken, use skip-grant-tables bootstrap.
        if (
            diagnosis["service_running"]
            and not diagnosis["connection_ok"]
            and not diagnosis["root_socket_ok"]
        ):
            print("\nServer is running but authentication is broken.")
            do_bootstrap = True
            if not skip_confirm:
                answer = input(
                    "Repair credentials with skip-grant-tables bootstrap? (yes/no) [yes]: "
                ).strip().lower()
                do_bootstrap = answer in {"", "y", "yes"}
            if do_bootstrap:
                if root_password is None and not skip_confirm:
                    set_root = input(
                        "Also set MariaDB root@localhost password during bootstrap? (yes/no) [no]: "
                    ).strip().lower()
                    if set_root in {"y", "yes"}:
                        root_password = getpass.getpass("Enter new root password: ").strip() or None

                if not self._bootstrap_with_skip_grant_tables(
                    admin_user,
                    admin_password,
                    admin_host=admin_host,
                    root_password=root_password,
                ):
                    print("ERROR: skip-grant-tables credential repair failed")
                    return False
                diagnosis = self._diagnose_mariadb()

        if not diagnosis["service_running"]:
            print("ERROR: MariaDB service is still not running after recovery attempts")
            if diagnosis.get("journal_tail"):
                print("\nRecent service log:")
                print(diagnosis["journal_tail"][-3000:])
            return False

        # After system table reset, root socket usually works; configure restore access.
        if diagnosis["root_socket_ok"]:
            if root_password is None and not skip_confirm:
                set_root = input("Set MariaDB root@localhost password? (yes/no) [no]: ").strip().lower()
                if set_root in {"y", "yes"}:
                    root_password = getpass.getpass("Enter new root password: ").strip()
                    if not root_password:
                        print("WARNING: Empty root password ignored")
                        root_password = None

            print("\nConfiguring restore access...")
            if not self._configure_restore_access(
                admin_user,
                admin_password,
                admin_host=admin_host,
                root_password=root_password,
            ):
                # Last-resort auth repair.
                print("Root socket configure failed; trying skip-grant-tables fallback...")
                if not self._bootstrap_with_skip_grant_tables(
                    admin_user,
                    admin_password,
                    admin_host=admin_host,
                    root_password=root_password,
                ):
                    return False
        elif not diagnosis["connection_ok"]:
            print("\nNo usable auth path; attempting skip-grant-tables recovery...")
            if not self._bootstrap_with_skip_grant_tables(
                admin_user,
                admin_password,
                admin_host=admin_host,
                root_password=root_password,
            ):
                return False
        else:
            print("\nConfig credentials already work.")
            if diagnosis["root_socket_ok"]:
                self._configure_restore_access(
                    admin_user,
                    admin_password,
                    admin_host=admin_host,
                    root_password=root_password,
                )

        host = self.config["mysql"].get("host", "localhost")
        port = self.config["mysql"].get("port", "3306")
        if not self._update_config_mysql_credentials(admin_user, admin_password, host=host, port=port):
            print("WARNING: Failed to update config file; restore user may still be configured in MariaDB")

        self.config.set("mysql", "user", admin_user)
        self.config.set("mysql", "password", admin_password)

        if not self._probe_connection(quiet=False):
            print("ERROR: Restore user credentials were configured but connection test failed")
            return False

        print("\n✓ Disaster recovery setup complete")
        print(f"  Restore user: {admin_user}@{admin_host}")
        print(f"  Config file: {os.path.abspath(self.config_file)}")

        if restore_path:
            print("\nProceeding to backup restore...")
            return self.restore_backup(
                restore_path,
                restore_as_slave=restore_as_slave,
                restore_mode=restore_mode,
                protected_restore=protected_restore,
                drop_non_system_databases=drop_non_system_databases,
                restart_after_restore=restart_after_restore,
            )

        return True

    def _run_restore_from_file(self, sql_file):
        """Run mysql restore from an existing SQL file path."""
        with open(sql_file, "r") as f:
            mysql = subprocess.Popen(
                ["mysql"] + self.get_mysql_connection_args(),
                stdin=f,
                stderr=subprocess.PIPE,
                text=True,
            )
            _, stderr = mysql.communicate()
            return mysql.returncode, stderr

    def _create_filtered_restore_file(self, db_file, is_compressed, skip_table):
        """Create temporary SQL file with INSERTs for selected table removed."""
        temp_sql = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False)
        temp_path = temp_sql.name
        temp_sql.close()

        skip_prefix = f"INSERT INTO `{skip_table}`"
        skipped_lines = 0

        if is_compressed:
            gunzip = subprocess.Popen(
                ["gunzip", "-c", db_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            source = gunzip.stdout
        else:
            gunzip = None
            source = open(db_file, "r")

        try:
            with open(temp_path, "w") as out:
                for line in source:
                    if line.startswith(skip_prefix):
                        skipped_lines += 1
                        continue
                    out.write(line)
        finally:
            if source:
                source.close()
            if gunzip:
                gunzip.wait()

        return temp_path, skipped_lines

    def _create_restore_file_without_system_schemas(
        self, db_file, is_compressed, include_schema=True, include_data=True
    ):
        """Create temporary SQL file with MariaDB system schemas removed.

        include_schema controls DDL/object statements (tables, views, routines, events, triggers, sequences).
        include_data controls INSERT rows.
        """
        temp_sql = tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False)
        temp_path = temp_sql.name
        temp_sql.close()

        skipped_dbs = set()
        skip_current_db = False

        if is_compressed:
            gunzip = subprocess.Popen(
                ["gunzip", "-c", db_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            source = gunzip.stdout
        else:
            gunzip = None
            source = open(db_file, "r")

        try:
            with open(temp_path, "w") as out:
                for line in source:
                    # mysqldump prints this before each schema when using --all-databases.
                    if line.startswith("-- Current Database: `"):
                        db_name = line.split("`", 2)[1]
                        skip_current_db = db_name in self.SYSTEM_SCHEMAS
                        if skip_current_db:
                            skipped_dbs.add(db_name)
                            continue

                    if line.startswith("CREATE DATABASE") or line.startswith("DROP DATABASE"):
                        if any(f"`{db}`" in line for db in self.SYSTEM_SCHEMAS):
                            continue

                    if line.startswith("USE `"):
                        db_name = line.split("`", 2)[1]
                        skip_current_db = db_name in self.SYSTEM_SCHEMAS
                        if skip_current_db:
                            skipped_dbs.add(db_name)
                            continue

                    if skip_current_db:
                        continue

                    if not include_data and line.startswith("INSERT INTO "):
                        continue

                    if not include_schema and (
                        line.startswith("DROP DATABASE")
                        or line.startswith("CREATE DATABASE")
                        or line.startswith("USE `")
                        or line.startswith("DROP TABLE")
                        or line.startswith("CREATE TABLE")
                        or line.startswith("DROP VIEW")
                        or line.startswith("CREATE ALGORITHM")
                        or line.startswith("CREATE VIEW")
                        or line.startswith("DROP TRIGGER")
                        or line.startswith("CREATE TRIGGER")
                        or line.startswith("DROP EVENT")
                        or line.startswith("CREATE EVENT")
                        or line.startswith("DROP PROCEDURE")
                        or line.startswith("CREATE PROCEDURE")
                        or line.startswith("DROP FUNCTION")
                        or line.startswith("CREATE FUNCTION")
                        or line.startswith("DROP SEQUENCE")
                        or line.startswith("CREATE SEQUENCE")
                        or line.startswith("ALTER TABLE")
                    ):
                        continue

                    out.write(line)

        finally:
            if source:
                source.close()
            if gunzip:
                gunzip.wait()

        return temp_path, sorted(skipped_dbs)

    def _resolve_restore_mode(self, restore_mode):
        """Normalize restore mode and derive include flags."""
        mode = (restore_mode or "full").strip().lower()
        if mode not in self.RESTORE_MODES:
            raise ValueError(
                f"Invalid restore mode '{restore_mode}'. Valid modes: {', '.join(sorted(self.RESTORE_MODES))}"
            )

        return {
            "mode": mode,
            "restore_users": mode in {"full", "users-grants"},
            "restore_databases": mode in {"full", "databases", "schema", "data"},
            "include_schema": mode in {"full", "databases", "schema"},
            "include_data": mode in {"full", "databases", "data"},
        }

    def _run_filtered_restore_stream(
        self,
        db_file,
        is_compressed,
        include_schema=True,
        include_data=True,
        skip_table=None,
    ):
        """Stream filtered SQL directly into mysql with progress updates."""
        estimated_total_bytes = self._estimate_restore_source_bytes(db_file, is_compressed)

        if is_compressed:
            gunzip = subprocess.Popen(
                ["gunzip", "-c", db_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            source = gunzip.stdout
        else:
            gunzip = None
            source = open(db_file, "r")

        mysql = subprocess.Popen(
            ["mysql"] + self.get_mysql_connection_args(),
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        skip_prefix = f"INSERT INTO `{skip_table}`" if skip_table else None
        skipped_table_inserts = 0
        skipped_dbs = set()
        skip_current_db = False
        processed_lines = 0
        total_bytes = 0
        started = time.time()
        last_report = started

        try:
            for line in source:
                if line.startswith("-- Current Database: `"):
                    db_name = line.split("`", 2)[1]
                    skip_current_db = db_name in self.SYSTEM_SCHEMAS
                    if skip_current_db:
                        skipped_dbs.add(db_name)
                        continue

                if line.startswith("CREATE DATABASE") or line.startswith("DROP DATABASE"):
                    if any(f"`{db}`" in line for db in self.SYSTEM_SCHEMAS):
                        continue

                if line.startswith("USE `"):
                    db_name = line.split("`", 2)[1]
                    skip_current_db = db_name in self.SYSTEM_SCHEMAS
                    if skip_current_db:
                        skipped_dbs.add(db_name)
                        continue

                if skip_current_db:
                    continue

                if skip_prefix and line.startswith(skip_prefix):
                    skipped_table_inserts += 1
                    continue

                if not include_data and line.startswith("INSERT INTO "):
                    continue

                if not include_schema and (
                    line.startswith("DROP DATABASE")
                    or line.startswith("CREATE DATABASE")
                    or line.startswith("USE `")
                    or line.startswith("DROP TABLE")
                    or line.startswith("CREATE TABLE")
                    or line.startswith("DROP VIEW")
                    or line.startswith("CREATE ALGORITHM")
                    or line.startswith("CREATE VIEW")
                    or line.startswith("DROP TRIGGER")
                    or line.startswith("CREATE TRIGGER")
                    or line.startswith("DROP EVENT")
                    or line.startswith("CREATE EVENT")
                    or line.startswith("DROP PROCEDURE")
                    or line.startswith("CREATE PROCEDURE")
                    or line.startswith("DROP FUNCTION")
                    or line.startswith("CREATE FUNCTION")
                    or line.startswith("DROP SEQUENCE")
                    or line.startswith("CREATE SEQUENCE")
                    or line.startswith("ALTER TABLE")
                ):
                    continue

                mysql.stdin.write(line)
                processed_lines += 1
                total_bytes += len(line.encode("utf-8", errors="ignore"))

                now = time.time()
                if now - last_report >= 2:
                    mb = total_bytes / (1024 * 1024)
                    elapsed = int(now - started)
                    spinner = self._spinner_frame(now - started)
                    if estimated_total_bytes and estimated_total_bytes > 0:
                        percent = min((total_bytes / estimated_total_bytes) * 100, 100.0)
                        eta = self._format_eta(total_bytes, estimated_total_bytes, elapsed)
                        self._update_dynamic_progress_line(
                            f"  → {spinner} {self._progress_bar(percent)} {percent:5.1f}% | {mb:.1f}/{estimated_total_bytes / (1024 * 1024):.1f} MB | {processed_lines:,} lines | elapsed {elapsed}s | eta {eta}"
                        )
                    else:
                        self._update_dynamic_progress_line(
                            f"  → {spinner} {self._progress_bar(0)}  --.-% | {mb:.1f} MB streamed | {processed_lines:,} lines | elapsed {elapsed}s"
                        )
                    last_report = now

            mysql.stdin.close()
            stderr = mysql.stderr.read()
            mysql.wait()
            if estimated_total_bytes and estimated_total_bytes > 0:
                elapsed = int(time.time() - started)
                final_mb = total_bytes / (1024 * 1024)
                total_mb = estimated_total_bytes / (1024 * 1024)
                self._update_dynamic_progress_line(
                    f"  → {self._spinner_frame(time.time() - started)} {self._progress_bar(100)} 100.0% | {final_mb:.1f}/{total_mb:.1f} MB | {processed_lines:,} lines | elapsed {elapsed}s"
                )
            else:
                elapsed = int(time.time() - started)
                final_mb = total_bytes / (1024 * 1024)
                self._update_dynamic_progress_line(
                    f"  → {self._spinner_frame(time.time() - started)} {self._progress_bar(100)} done | {final_mb:.1f} MB streamed | {processed_lines:,} lines | elapsed {elapsed}s"
                )

            self._finish_dynamic_progress_line()
            return (
                mysql.returncode,
                stderr,
                sorted(skipped_dbs),
                skipped_table_inserts,
                processed_lines,
                total_bytes,
            )
        finally:
            self._finish_dynamic_progress_line()
            try:
                if source:
                    source.close()
            except Exception:
                pass
            if gunzip:
                gunzip.wait()

    def _estimate_restore_source_bytes(self, db_file, is_compressed):
        """Estimate total bytes to stream for percent progress display."""
        if not is_compressed:
            try:
                return os.path.getsize(db_file)
            except OSError:
                return None

        # Prefer gzip metadata for O(1) estimate.
        try:
            result = subprocess.run(
                ["gzip", "-l", db_file],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
                if len(lines) >= 2:
                    # Output format: compressed uncompressed ratio uncompressed_name
                    parts = lines[-1].split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        uncompressed = int(parts[1])
                        if uncompressed > 0:
                            return uncompressed
        except Exception:
            pass

        # Fallback to gzip footer size (may wrap for files >4GB).
        try:
            with open(db_file, "rb") as f:
                f.seek(-4, os.SEEK_END)
                raw = f.read(4)
                if len(raw) == 4:
                    return int.from_bytes(raw, "little") or None
        except Exception:
            pass

        return None

    def _progress_bar(self, percent, width=24):
        """Render a simple ASCII progress bar for restore stream."""
        pct = max(0.0, min(percent, 100.0))
        filled = int(round((pct / 100.0) * width))
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def _spinner_frame(self, elapsed_seconds):
        """Return a simple activity spinner frame."""
        frames = ["|", "/", "-", "\\"]
        idx = int(elapsed_seconds * 4) % len(frames)
        return frames[idx]

    def _update_dynamic_progress_line(self, text):
        """Update a single in-place progress line in terminal output."""
        if not hasattr(self, "_progress_line_len"):
            self._progress_line_len = 0

        padding = max(self._progress_line_len - len(text), 0)
        sys.stdout.write("\r" + text + (" " * padding))
        sys.stdout.flush()
        self._progress_line_len = len(text)

    def _finish_dynamic_progress_line(self):
        """Finalize an in-place progress line with a newline."""
        if hasattr(self, "_progress_line_len") and self._progress_line_len > 0:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._progress_line_len = 0

    def _format_eta(self, processed_bytes, total_bytes, elapsed_seconds):
        """Estimate ETA from current throughput."""
        if not total_bytes or processed_bytes <= 0 or elapsed_seconds <= 0:
            return "--"

        remaining = max(total_bytes - processed_bytes, 0)
        rate = processed_bytes / elapsed_seconds
        if rate <= 0:
            return "--"

        eta_seconds = int(remaining / rate)
        mins, secs = divmod(eta_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h{mins:02d}m"
        return f"{mins:02d}m{secs:02d}s"

    def _restore_users_and_grants(self, users_restore_file, is_users_compressed):
        """Restore users/grants file and return True/False based on mysql exit code."""
        if is_users_compressed:
            gunzip = subprocess.Popen(
                ["gunzip", "-c", users_restore_file], stdout=subprocess.PIPE
            )
            mysql = subprocess.Popen(
                ["mysql", "--force"] + self.get_mysql_connection_args(),
                stdin=gunzip.stdout,
                stderr=subprocess.PIPE,
                text=True,
            )
            gunzip.stdout.close()
            _, stderr = mysql.communicate()
        else:
            with open(users_restore_file, "r") as f:
                mysql = subprocess.Popen(
                    ["mysql", "--force"] + self.get_mysql_connection_args(),
                    stdin=f,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                _, stderr = mysql.communicate()

        if mysql.returncode != 0:
            print(
                f"WARNING: Users/grants restore returned non-zero status: {self._format_restore_error(stderr)}"
            )
            return False

        return True

    def test_connection(self):
        """Test MySQL connection"""
        try:
            # Check if required config values are present
            if not self.config.get('mysql', 'password', fallback=''):
                print("WARNING: MySQL password is empty")
            
            # Show connection method being used
            host = self.config['mysql']['host']
            user = self.config['mysql']['user']
            host_to_use = host
            use_tcp = False
            
            if host.lower() == 'localhost':
                print(f"Attempting connection as {user} via Unix socket...")
                
                # Check for socket file
                socket_locations = [
                    '/var/run/mysqld/mysqld.sock',
                    '/var/lib/mysql/mysql.sock',
                    '/tmp/mysql.sock',
                    '/run/mysqld/mysqld.sock',
                ]
                socket_found = False
                for sock in socket_locations:
                    if os.path.exists(sock):
                        print(f"  Found socket: {sock}")
                        socket_found = True
                        break
                if not socket_found:
                    print("  Warning: Standard MySQL socket file not found")
            else:
                use_tcp = True
                host_to_use = host
                
            if use_tcp:
                print(f"Attempting connection to {host_to_use}:{self.config['mysql']['port']} as {user}...")
            elif host.lower() == 'localhost':
                print(f"Attempting connection as {user} via Unix socket...")
                
                # Check for common socket file locations
                socket_locations = [
                    '/var/run/mysqld/mysqld.sock',
                    '/var/lib/mysql/mysql.sock',
                    '/tmp/mysql.sock',
                    '/run/mysqld/mysqld.sock',
                ]
                socket_found = False
                for sock in socket_locations:
                    if os.path.exists(sock):
                        print(f"  Found socket: {sock}")
                        socket_found = True
                        break
                if not socket_found:
                    print("  Warning: Standard MySQL socket file not found")
            else:
                port = self.config['mysql']['port']
                print(f"Attempting connection to {host}:{port} as {user}...")
            
            # Check if mysql client exists
            check_mysql = subprocess.run(['which', 'mysql'], capture_output=True, text=True)
            if check_mysql.returncode != 0:
                print("ERROR: 'mysql' command not found. Please install MySQL/MariaDB client.")
                return False
            
            # Add connection timeout and skip-reconnect to prevent hanging
            # --no-defaults prevents reading config files that might cause hanging
            # --skip-ssl avoids TLS handshake issues that can cause errors or hanging
            cmd = (
                ["mysql", "--no-defaults"]
                + self.get_mysql_connection_args(host_override=None)  # Use config host (localhost for socket)
                + [
                    "--skip-ssl",
                    "--connect-timeout=5",
                    "--skip-reconnect",
                    "--batch",
                    "--skip-column-names",
                    "-e", 
                    "SELECT 1;"
                ]
            )
            
            # Debug: show sanitized command
            sanitized_cmd = []
            for arg in cmd:
                if '--password=' in arg:
                    sanitized_cmd.append('--password=***')
                else:
                    sanitized_cmd.append(arg)
            print(f"  Command: {' '.join(sanitized_cmd)}")
            
            # Use MYSQL_PWD environment variable to avoid password warnings that might cause hanging
            # and stdin=DEVNULL to prevent any interactive prompts
            env = os.environ.copy()
            env['MYSQL_PWD'] = self.config['mysql']['password']
            
            # Remove password from command since we're using env var
            cmd_without_pwd = [arg for arg in cmd if not arg.startswith('--password=')]
            
            print(f"  Using MYSQL_PWD environment variable for password")
            print(f"  Connecting with 5 second MySQL timeout...")
            
            result = subprocess.run(
                cmd_without_pwd, 
                capture_output=True, 
                text=True, 
                timeout=10,
                stdin=subprocess.DEVNULL,
                env=env
            )
            
            if result.returncode != 0:
                # Show stderr but filter out password
                error_msg = result.stderr
                if error_msg:
                    # Replace password in error messages
                    password = self.config['mysql']['password']
                    if password:
                        error_msg = error_msg.replace(password, '***')
                    print(f"Connection error: {error_msg.strip()}")
                
                if host.lower() == 'localhost':
                    print(f"Could not connect to MySQL as {user} via Unix socket")
                    print("Try checking: sudo systemctl status mariadb (or mysql)")
                else:
                    print(f"Could not connect to MySQL at {host}:{port} as {user}")
                print("Verify MySQL is running and credentials are correct.")
                
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print(f"Connection test failed: Connection timed out after 10 seconds")
            if host.lower() == 'localhost':
                print("MySQL client is hanging. Possible causes:")
                print("  - MySQL/MariaDB service is not running")
                print("  - Unix socket file is missing or inaccessible")
                print("  - Try: sudo systemctl status mariadb")
            else:
                print("MySQL server is not responding. Verify it's running and accessible.")
            return False
        except Exception as e:
            print(f"Connection test failed: {type(e).__name__}: {str(e)}")
            return False

    def notify_backup_webhook(self, success, backup_type, backup_dir, message=None):
        """Send webhook notification if configured."""
        url_key = 'success_url' if success else 'failure_url'
        webhooks_cfg = self.config['webhooks'] if self.config.has_section('webhooks') else {}
        url = webhooks_cfg.get(url_key, '').strip() if hasattr(webhooks_cfg, 'get') else ''
        if not url:
            return

        payload = {
            "status": "success" if success else "failure",
            "backup_type": backup_type,
            "backup_dir": backup_dir,
            "backup_name": os.path.basename(backup_dir) if backup_dir else None,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
        if message:
            payload["message"] = message

        # Include simple size info when available
        if backup_dir and os.path.exists(backup_dir):
            try:
                size_bytes = sum(
                    os.path.getsize(os.path.join(backup_dir, f))
                    for f in os.listdir(backup_dir)
                    if os.path.isfile(os.path.join(backup_dir, f))
                )
                payload["size_bytes"] = size_bytes
            except OSError:
                pass

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            print(f"Webhook sent to {url_key}: {url}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"WARNING: Failed to send webhook to {url}: {e}")
        except Exception as e:  # Fallback for unexpected issues
            print(f"WARNING: Unexpected error while sending webhook: {e}")

    def get_master_status(self):
        """Get master replication status"""
        try:
            cmd = (
                ["mysql"]
                + self.get_mysql_connection_args()
                + ["-N", "-B", "-e", "SHOW MASTER STATUS;"]
            )
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("\t")
                if len(parts) >= 2:
                    return {
                        "binlog_file": parts[0],
                        "binlog_position": parts[1],
                        "binlog_do_db": parts[2] if len(parts) > 2 else "",
                        "binlog_ignore_db": parts[3] if len(parts) > 3 else "",
                    }
            return None
        except Exception as e:
            print(f"Error getting master status: {e}")
            return None

    def backup_databases(self, backup_type="manual", backup_path=None):
        """
        Backup all databases with users, grants, and replication info

        Args:
            backup_type: 'hourly', 'daily', 'monthly', or 'manual'
            backup_path: Override backup path from config
        """
        print(f"\n{'='*60}")
        print(f"Starting {backup_type.upper()} Backup")
        print(f"{'='*60}\n")

        # Determine backup directory
        if backup_path:
            base_dir = backup_path
        elif backup_type in ["hourly", "daily", "monthly"]:
            base_dir = self.config["backup_paths"][backup_type]
        else:
            base_dir = self.config["backup_paths"].get(
                "daily", "/var/backups/mariadb/manual"
            )

        # Create base directory
        os.makedirs(base_dir, exist_ok=True)

        # Generate backup name based on type
        now = datetime.datetime.now()
        if backup_type == "hourly":
            # Same hour overwrites: hourly_YYYYMMDD_HH
            backup_name = f"hourly_{now.strftime('%Y%m%d_%H')}"
        elif backup_type == "daily":
            # Same day overwrites: daily_YYYYMMDD
            backup_name = f"daily_{now.strftime('%Y%m%d')}"
        elif backup_type == "monthly":
            # Same month overwrites: monthly_YYYYMM
            backup_name = f"monthly_{now.strftime('%Y%m')}"
        else:
            # Manual/other: full timestamp
            backup_name = f"manual_{now.strftime('%Y%m%d_%H%M%S')}"

        backup_dir = os.path.join(base_dir, f"backup_{backup_name}")

        # Remove existing backup if it exists (for overwrite behavior)
        if os.path.exists(backup_dir):
            print(f"Removing existing backup: {backup_dir}")
            shutil.rmtree(backup_dir)

        os.makedirs(backup_dir, exist_ok=True)

        print(f"Backup directory: {backup_dir}")

        def notify_failure(reason):
            self.notify_backup_webhook(False, backup_type, backup_dir, reason)
            return False

        # Test connection
        if not self.test_connection():
            print("ERROR: Cannot connect to MySQL. Check your credentials.")
            return notify_failure("MySQL connection failed")

        print("✓ MySQL connection successful")

        # Get master status for replication
        master_status = self.get_master_status()

        # 1. Backup all databases
        print("\n[1/5] Backing up all databases...")
        db_backup_file = os.path.join(backup_dir, "all_databases.sql")

        mysqldump_cmd = (
            ["mysqldump"]
            + self.get_mysql_connection_args()
            + [
                "--all-databases",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--events",
                "--flush-privileges",
                "--hex-blob",
                "--master-data=2",  # Comments out CHANGE MASTER command
                "--add-drop-database",
                "--quick",
            ]
        )

        try:
            with open(db_backup_file, "w") as f:
                result = subprocess.run(
                    mysqldump_cmd, stdout=f, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL
                )

            if result.returncode != 0:
                print(f"ERROR: Database backup failed: {result.stderr}")
                return notify_failure("Database backup failed")

            print(
                f"✓ Database backup completed: {os.path.getsize(db_backup_file)} bytes"
            )
        except Exception as e:
            print(f"ERROR: Database backup failed: {e}")
            return notify_failure("Database backup crashed")

        # 2. Backup users and grants
        print("\n[2/5] Backing up users and grants...")
        users_file = os.path.join(backup_dir, "users_and_grants.sql")

        try:
            # Get all users
            get_users_cmd = (
                ["mysql"]
                + self.get_mysql_connection_args()
                + [
                    "-N",
                    "-B",
                    "-e",
                    "SELECT DISTINCT user, host FROM mysql.user WHERE user NOT IN ('mysql.sys', 'mariadb.sys', 'mysql.infoschema', 'mysql.session');",
                ]
            )
            result = subprocess.run(get_users_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)

            with open(users_file, "w") as f:
                f.write("-- Users and Grants Backup\n")
                f.write(f"-- Created: {datetime.datetime.now()}\n\n")

                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split("\t")
                        if len(parts) == 2:
                            user, host = parts

                            # Get CREATE USER statement
                            show_create_cmd = (
                                ["mysql"]
                                + self.get_mysql_connection_args()
                                + [
                                    "-N",
                                    "-B",
                                    "-e",
                                    f"SHOW CREATE USER '{user}'@'{host}';",
                                ]
                            )
                            create_result = subprocess.run(
                                show_create_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL
                            )
                            if create_result.returncode == 0:
                                f.write(f"{create_result.stdout.strip()};\n")

                            # Get GRANTS
                            show_grants_cmd = (
                                ["mysql"]
                                + self.get_mysql_connection_args()
                                + [
                                    "-N",
                                    "-B",
                                    "-e",
                                    f"SHOW GRANTS FOR '{user}'@'{host}';",
                                ]
                            )
                            grants_result = subprocess.run(
                                show_grants_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL
                            )
                            if grants_result.returncode == 0:
                                for grant_line in grants_result.stdout.strip().split(
                                    "\n"
                                ):
                                    if grant_line.strip():
                                        f.write(f"{grant_line.strip()};\n")

                            f.write("\n")

            print(f"✓ Users and grants backup completed")
        except Exception as e:
            print(f"WARNING: Users backup failed: {e}")

        # 3. Save replication information
        print("\n[3/5] Saving replication information...")
        repl_info_file = os.path.join(backup_dir, "replication_info.json")

        replication_info = {
            "backup_time": now.isoformat(),
            "backup_type": backup_type,
            "master_status": master_status,
            "server_id": None,
            "server_uuid": None,
        }

        # Get server ID
        try:
            cmd = (
                ["mysql"]
                + self.get_mysql_connection_args()
                + ["-N", "-B", "-e", "SELECT @@server_id;"]
            )
            result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if result.returncode == 0:
                replication_info["server_id"] = result.stdout.strip()
        except:
            pass

        # Get server UUID
        try:
            cmd = (
                ["mysql"]
                + self.get_mysql_connection_args()
                + ["-N", "-B", "-e", "SELECT @@server_uuid;"]
            )
            result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if result.returncode == 0:
                replication_info["server_uuid"] = result.stdout.strip()
        except:
            pass

        with open(repl_info_file, "w") as f:
            json.dump(replication_info, f, indent=2)

        print(f"✓ Replication info saved")
        if master_status:
            print(
                f"  Master binlog: {master_status['binlog_file']}:{master_status['binlog_position']}"
            )

        # 4. Create backup manifest
        print("\n[4/5] Creating backup manifest...")
        manifest_file = os.path.join(backup_dir, "MANIFEST.txt")

        with open(manifest_file, "w") as f:
            f.write(f"MariaDB Backup Manifest\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"Backup Type: {backup_type}\n")
            f.write(f"Backup Time: {now}\n")
            f.write(f"Backup Name: {backup_name}\n")
            f.write(f"Backup Directory: {backup_dir}\n\n")

            f.write(f"Files:\n")
            for item in os.listdir(backup_dir):
                if item != "MANIFEST.txt":
                    item_path = os.path.join(backup_dir, item)
                    size = os.path.getsize(item_path)
                    f.write(f"  - {item} ({size:,} bytes)\n")

            f.write(f"\nReplication Status:\n")
            if master_status:
                f.write(f"  Binlog File: {master_status['binlog_file']}\n")
                f.write(f"  Binlog Position: {master_status['binlog_position']}\n")
            else:
                f.write(f"  Not available (not a master or binary logging disabled)\n")

        print(f"✓ Manifest created")

        # 5. Compress if enabled
        if self.config["options"].get("compression", "yes").lower() == "yes":
            print("\n[5/5] Compressing backup...")
            try:
                subprocess.run(["gzip", "-f", db_backup_file], check=True)
                print(f"✓ Database file compressed")

                subprocess.run(["gzip", "-f", users_file], check=True)
                print(f"✓ Users file compressed")
            except Exception as e:
                print(f"WARNING: Compression failed: {e}")
        else:
            print("\n[5/5] Compression disabled")

        # Step 6: Rotation - Clean up old backups
        print("\n[6/6] Cleaning up old backups...")
        self.rotate_backups(backup_type, base_dir)

        print(f"\n{'='*60}")
        print(f"Backup completed successfully!")
        print(f"Location: {backup_dir}")
        print(f"{'='*60}\n")
        self.notify_backup_webhook(True, backup_type, backup_dir, "Backup completed")
        return True

    def rotate_backups(self, backup_type, base_dir):
        """
        Rotate backups by removing old ones based on retention policy.
        
        Args:
            backup_type: Type of backup ('hourly', 'daily', 'monthly')
            base_dir: Base directory where backups are stored
        """
        # Get retention limit from config
        keep_count = self.config['rotation'].getint(f'{backup_type}_keep', 0)
        
        if keep_count <= 0:
            print(f"Rotation disabled for {backup_type} backups (keep_count: {keep_count})")
            return
        
        print(f"Keeping last {keep_count} {backup_type} backups...")
        
        # Find all backup directories in this location
        backup_dirs = []
        if os.path.exists(base_dir):
            for item in os.listdir(base_dir):
                item_path = os.path.join(base_dir, item)
                # Match backup directories for this specific type
                if os.path.isdir(item_path) and item.startswith(f"backup_{backup_type}_"):
                    # Get modification time
                    mtime = os.path.getmtime(item_path)
                    backup_dirs.append((item_path, mtime, item))
        
        # Sort by modification time (newest first)
        backup_dirs.sort(key=lambda x: x[1], reverse=True)
        
        # Keep the newest keep_count backups, delete the rest
        deleted_count = 0
        for i, (backup_path, mtime, name) in enumerate(backup_dirs):
            if i >= keep_count:
                try:
                    shutil.rmtree(backup_path)
                    deleted_count += 1
                    print(f"  Deleted old backup: {name}")
                except Exception as e:
                    print(f"  WARNING: Failed to delete {name}: {e}")
        
        if deleted_count > 0:
            print(f"Deleted {deleted_count} old backup(s)")
        else:
            print(f"No old backups to delete (total: {len(backup_dirs)}, keeping: {keep_count})")

    def list_backups(self, backup_type=None):
        """List available backups"""
        print(f"\n{'='*60}")
        print("Available Backups")
        print(f"{'='*60}\n")

        types_to_check = (
            ["hourly", "daily", "monthly"] if backup_type is None else [backup_type]
        )

        all_backups = []

        for btype in types_to_check:
            path = self.config["backup_paths"].get(btype)
            if path and os.path.exists(path):
                try:
                    items = os.listdir(path)
                except (OSError, IOError, PermissionError) as e:
                    print(f"Warning: Could not read {btype} backup directory {path}: {e}")
                    continue
                    
                for item in items:
                    try:
                        item_path = os.path.join(path, item)
                        # Skip if we can't access the item (broken symlinks, permission issues)
                        if not os.path.exists(item_path):
                            continue
                            
                        # Match both old and new naming patterns for backwards compatibility
                        if os.path.isdir(item_path) and (item.startswith(f"backup_{btype}_") or (item.startswith("backup_") and not any(item.startswith(f"backup_{t}_") for t in ["hourly", "daily", "monthly", "manual"]))):
                            manifest_file = os.path.join(item_path, "MANIFEST.txt")
                            if os.path.exists(manifest_file):
                                mtime = os.path.getmtime(item_path)
                                all_backups.append(
                                    {
                                        "type": btype,
                                        "name": item,
                                        "path": item_path,
                                        "mtime": mtime,
                                    }
                                )
                    except (OSError, IOError, PermissionError) as e:
                        # Skip items we can't access
                        print(f"Warning: Could not access backup item {item}: {e}")
                        continue


        if not all_backups:
            print("No backups found.")
            return []

        # Sort by modification time (newest first)
        all_backups.sort(key=lambda x: x["mtime"], reverse=True)

        for idx, backup in enumerate(all_backups, 1):
            backup_time = datetime.datetime.fromtimestamp(backup["mtime"])
            
            # Calculate size with error handling
            size = 0
            size_error = False
            try:
                for f in os.listdir(backup["path"]):
                    file_path = os.path.join(backup["path"], f)
                    try:
                        if os.path.isfile(file_path) and not os.path.islink(file_path):
                            size += os.path.getsize(file_path)
                    except (OSError, IOError) as e:
                        # Skip files we can't read
                        size_error = True
                        continue
            except (OSError, IOError) as e:
                size_error = True
                print(f"   Warning: Could not read some files in backup directory: {e}")

            print(f"{idx}. [{backup['type'].upper()}] {backup['name']}")
            print(f"   Time: {backup_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if size_error:
                print(f"   Size: ~{size:,} bytes (~{size/1024/1024:.2f} MB) [incomplete]")
            else:
                print(f"   Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
            print(f"   Path: {backup['path']}")
            print()

        return all_backups

    def _drop_non_system_databases(self):
        """Drop all non-system schemas before restore (destructive)."""
        query = (
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT IN ('mysql','information_schema','performance_schema','sys');"
        )
        code, stdout, stderr = self._run_mysql_sql(query)
        if code != 0:
            print(
                f"ERROR: Could not list databases for drop operation: {stderr or 'unknown error'}"
            )
            return False

        schemas = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not schemas:
            print("No non-system databases found to drop.")
            return True

        total = len(schemas)
        started = time.time()
        print(f"Dropping {total} non-system database(s)...")
        self._update_dynamic_progress_line(
            f"  → {self._spinner_frame(0)} {self._progress_bar(0)}   0.0% | 0/{total} databases dropped"
        )

        for idx, schema in enumerate(schemas, 1):
            escaped = schema.replace("`", "``")
            drop_sql = f"DROP DATABASE IF EXISTS `{escaped}`;"
            dcode, _, dstderr = self._run_mysql_sql(drop_sql)
            if dcode != 0:
                self._finish_dynamic_progress_line()
                print(
                    f"ERROR: Failed to drop database '{schema}': {dstderr or 'unknown error'}"
                )
                return False

            pct = (idx / total) * 100
            self._update_dynamic_progress_line(
                f"  → {self._spinner_frame(time.time() - started)} {self._progress_bar(pct)} {pct:5.1f}% | {idx}/{total} databases dropped"
            )

        self._finish_dynamic_progress_line()

        print(f"✓ Dropped {len(schemas)} non-system database(s)")
        return True

    def restore_backup(
        self,
        backup_path,
        restore_as_slave=False,
        master_host=None,
        master_user=None,
        master_password=None,
        master_port=None,
        restore_mode="full",
        protected_restore=True,
        drop_non_system_databases=False,
        restart_after_restore=True,
    ):
        """
        Restore a backup

        Args:
            backup_path: Path to backup directory
            restore_as_slave: Whether to configure as replication slave
            master_host: Master server hostname/IP (for slave setup, defaults to config)
            master_user: Master replication user (for slave setup, defaults to config)
            master_password: Master replication password (for slave setup, defaults to config)
            master_port: Master server port (for slave setup, defaults to config)
            restore_mode: What to restore: full, users-grants, databases, schema, data
            protected_restore: Enable restore safety mode (read_only ON, event_scheduler OFF)
            drop_non_system_databases: Drop non-system schemas before restore (destructive)
            restart_after_restore: Restart MariaDB service after restore (recommended safety reset)
        """
        print(f"\n{'='*60}")
        print(f"Restoring Backup")
        print(f"{'='*60}\n")

        if not os.path.exists(backup_path):
            print(f"ERROR: Backup path not found: {backup_path}")
            return False

        print(f"Backup location: {backup_path}")

        try:
            restore_opts = self._resolve_restore_mode(restore_mode)
        except ValueError as e:
            print(f"ERROR: {e}")
            return False

        selected_mode = restore_opts["mode"]
        restore_users = restore_opts["restore_users"]
        restore_databases = restore_opts["restore_databases"]
        include_schema = restore_opts["include_schema"]
        include_data = restore_opts["include_data"]

        mode_descriptions = {
            "full": "Databases + users/grants",
            "users-grants": "Users and grants only",
            "databases": "Databases only (schema + data + routines/functions/events/triggers/sequences)",
            "schema": "Database schema/objects only (tables/views/routines/functions/events/triggers/sequences)",
            "data": "Database data only (INSERT rows)",
        }
        print(f"Restore mode: {selected_mode} - {mode_descriptions[selected_mode]}")

        # Check for required files
        db_backup_file = os.path.join(backup_path, "all_databases.sql")
        db_backup_gz = os.path.join(backup_path, "all_databases.sql.gz")
        users_file = os.path.join(backup_path, "users_and_grants.sql")
        users_gz = os.path.join(backup_path, "users_and_grants.sql.gz")
        repl_info_file = os.path.join(backup_path, "replication_info.json")

        # Determine which files exist
        if os.path.exists(db_backup_gz):
            db_file = db_backup_gz
            is_compressed = True
        elif os.path.exists(db_backup_file):
            db_file = db_backup_file
            is_compressed = False
        else:
            print("ERROR: Database backup file not found")
            return False

        # Load replication info
        replication_info = None
        if os.path.exists(repl_info_file):
            with open(repl_info_file, "r") as f:
                replication_info = json.load(f)

        # Confirm restoration
        print(f"\n⚠️  WARNING: This will REPLACE all databases on the target server!")
        print(
            f"   Target: {self.config['mysql']['host']}:{self.config['mysql']['port']}"
        )
        print(f"   Protected restore: {'ENABLED' if protected_restore else 'DISABLED'}")
        print(
            f"   Drop non-system DBs first: {'YES' if drop_non_system_databases else 'NO'}"
        )
        print(
            f"   Restart MariaDB after restore: {'YES' if restart_after_restore else 'NO'}"
        )

        if restore_as_slave:
            print(f"   Mode: SLAVE (replication will be configured)")
            
            # Use config defaults if not provided
            if not master_host and self.config.has_section('replication'):
                master_host = self.config['replication'].get('master_host', '')
            if not master_user and self.config.has_section('replication'):
                master_user = self.config['replication'].get('master_user', '')
            if not master_password and self.config.has_section('replication'):
                master_password = self.config['replication'].get('master_password', '')
            if not master_port and self.config.has_section('replication'):
                master_port = self.config['replication'].get('master_port', '3306')
            else:
                master_port = master_port or '3306'
            
            if not master_host:
                print(f"   ERROR: Master host required for slave setup")
                print(f"   Hint: Set in config file [replication] section or pass as parameter")
                return False
        else:
            print(f"   Mode: STANDALONE/MASTER")

        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Restore cancelled.")
            return False

        # Test connection
        if not self.test_connection():
            print("ERROR: Cannot connect to MySQL. Check your credentials.")
            return False

        # Preflight packet size check (server-side)
        global_packet, session_packet = self._get_server_packet_sizes()
        if global_packet and session_packet:
            print(
                f"Server packet limits: global={global_packet} bytes, session={session_packet} bytes"
            )
            if global_packet < 268435456:
                print(
                    "WARNING: Server global max_allowed_packet is below 256MB; large BLOB rows may fail during restore."
                )
                if self._try_raise_global_packet_size(1073741824):
                    new_global, new_session = self._get_server_packet_sizes()
                    print(
                        f"✓ Raised global max_allowed_packet: global={new_global} bytes, session={new_session} bytes"
                    )
                else:
                    print(
                        "WARNING: Could not raise global max_allowed_packet automatically (insufficient privileges or server restriction)."
                    )

        protected_state = None
        if protected_restore:
            print("\nEnabling protected restore mode (read_only=ON, event_scheduler=OFF)...")
            ok, protected_state, error = self._enable_protected_restore()
            if not ok:
                print(f"ERROR: {error}")
                return False
            print("✓ Protected restore mode enabled")
        else:
            print("\nWARNING: Protected restore mode disabled by user")

        if drop_non_system_databases:
            if not restore_databases:
                print(
                    "WARNING: Drop non-system DBs requested but restore mode does not include database restore"
                )
            else:
                print("\nRunning destructive pre-restore cleanup: dropping non-system databases...")
                if not self._drop_non_system_databases():
                    return False

        try:
            # Locate users/grants restore source first so definers exist before routines are created.
            if os.path.exists(users_gz):
                users_restore_file = users_gz
                is_users_compressed = True
            elif os.path.exists(users_file):
                users_restore_file = users_file
                is_users_compressed = False
            else:
                print("WARNING: Users backup file not found, skipping")
                users_restore_file = None

            total_steps = 0
            if restore_users and users_restore_file:
                total_steps += 1
            if restore_databases:
                total_steps += 1
            if restore_users and users_restore_file and restore_databases:
                total_steps += 1
            will_configure_slave = (
                restore_as_slave and replication_info and replication_info.get("master_status")
            )
            if will_configure_slave:
                total_steps += 1

            step = 1

            # 1. Restore users/grants first to satisfy DEFINER accounts for routines/functions.
            if restore_users and users_restore_file:
                print(f"\n[{step}/{total_steps}] Restoring users and grants (pre-pass)...")
                try:
                    if self._restore_users_and_grants(users_restore_file, is_users_compressed):
                        print("✓ Users and grants pre-pass restored")
                    else:
                        print("WARNING: Users/grants pre-pass had SQL errors (continuing)")
                except Exception as e:
                    print(f"WARNING: Users restore pre-pass had errors: {e}")
                step += 1
            elif restore_users and not users_restore_file:
                print("WARNING: Restore mode requires users/grants but users backup file is missing")

            # 2. Restore databases
            if restore_databases:
                print(f"\n[{step}/{total_steps}] Restoring databases...")
                try:
                    print("  → Preparing restore stream (excluding system schemas: mysql, information_schema, performance_schema, sys)...")
                    print(f"  → Component filter: include_schema={include_schema}, include_data={include_data}")
                    code, stderr, skipped_system_dbs, skipped_bw_inserts, sent_lines, sent_bytes = self._run_filtered_restore_stream(
                        db_file,
                        is_compressed,
                        include_schema=include_schema,
                        include_data=include_data,
                    )
                    if skipped_system_dbs:
                        print(f"  → Skipping system schemas from dump: {', '.join(skipped_system_dbs)}")
                    print(
                        f"  → Streamed {sent_lines:,} SQL lines ({sent_bytes / (1024 * 1024):.1f} MB) to mysql"
                    )

                    if code != 0:
                        lowered = (stderr or "").lower()
                        if "server has gone away" in lowered and "bw_jobs_cache" in lowered:
                            print(
                                "WARNING: Restore failed on oversized bw_jobs_cache row; retrying while skipping bw_jobs_cache INSERTs..."
                            )
                            code, retry_stderr, skipped_system_dbs, skipped, sent_lines, sent_bytes = self._run_filtered_restore_stream(
                                db_file,
                                is_compressed,
                                include_schema=include_schema,
                                include_data=include_data,
                                skip_table="bw_jobs_cache",
                            )
                            if code != 0:
                                print(
                                    f"ERROR: Database restore failed after fallback retry: {self._format_restore_error(retry_stderr)}"
                                )
                                return False
                            print(
                                f"✓ Databases restored with fallback (skipped {skipped} bw_jobs_cache INSERT statement(s))"
                            )
                        else:
                            print(f"ERROR: Database restore failed: {self._format_restore_error(stderr)}")
                            return False

                    if code == 0:
                        print("✓ Databases restored successfully")
                except Exception as e:
                    print(f"ERROR: Database restore failed: {e}")
                    return False
                step += 1

            # 3. Restore users/grants again so permissions are fully applied after schema/data import.
            if restore_users and users_restore_file and restore_databases:
                print(f"\n[{step}/{total_steps}] Restoring users and grants (post-pass)...")
                try:
                    if self._restore_users_and_grants(users_restore_file, is_users_compressed):
                        print("✓ Users and grants post-pass restored")
                    else:
                        print("WARNING: Users/grants post-pass had SQL errors")
                except Exception as e:
                    print(f"WARNING: Users restore had errors: {e}")
                step += 1

            # 4. Configure replication if requested
            if (
                restore_as_slave
                and replication_info
                and replication_info.get("master_status")
            ):
                print(f"\n[{step}/{total_steps}] Configuring slave replication...")

                master_status = replication_info["master_status"]

                if not master_user or not master_password:
                    print("ERROR: Master user and password required for slave setup")
                    return False

                try:
                    # Stop slave if running and reset any existing configuration
                    print("  → Stopping any existing slave processes...")
                    cmd = (
                        ["mysql"] + self.get_mysql_connection_args() + ["-e", "STOP SLAVE;"]
                    )
                    subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)

                    print("  → Resetting slave configuration...")
                    cmd = (
                        ["mysql"] + self.get_mysql_connection_args() + ["-e", "RESET SLAVE ALL;"]
                    )
                    subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)

                    # Configure slave
                    print("  → Configuring master connection...")
                    change_master_sql = f"""
                    CHANGE MASTER TO
                        MASTER_HOST='{master_host}',
                        MASTER_USER='{master_user}',
                        MASTER_PASSWORD='{master_password}',
                        MASTER_PORT={master_port},
                        MASTER_LOG_FILE='{master_status['binlog_file']}',
                        MASTER_LOG_POS={master_status['binlog_position']};
                    """

                    cmd = (
                        ["mysql"]
                        + self.get_mysql_connection_args()
                        + ["-e", change_master_sql]
                    )
                    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)

                    if result.returncode != 0:
                        print(f"ERROR: Failed to configure slave: {result.stderr}")
                        print("\nTroubleshooting tips:")
                        print("  1. Check MariaDB error log: journalctl -u mariadb -n 50")
                        print("  2. Verify master server is accessible")
                        print("  3. Verify master user has REPLICATION SLAVE privilege")
                        return False

                    # Start slave
                    print("  → Starting slave replication...")
                    cmd = (
                        ["mysql"]
                        + self.get_mysql_connection_args()
                        + ["-e", "START SLAVE;"]
                    )
                    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)

                    if result.returncode != 0:
                        print(f"ERROR: Failed to start slave: {result.stderr}")
                        return False

                    # Check slave status
                    print("  → Checking slave status...")
                    cmd = (
                        ["mysql"]
                        + self.get_mysql_connection_args()
                        + ["-e", "SHOW SLAVE STATUS\\G"]
                    )
                    result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)

                    print("✓ Slave replication configured")
                    print("\nSlave Status:")
                    print(result.stdout)

                except Exception as e:
                    print(f"ERROR: Slave configuration failed: {e}")
                    return False
            else:
                if restore_as_slave:
                    print("\nSkipping replication configuration (replication metadata not found in backup)")

            print(f"\n{'='*60}")
            print("Restore completed successfully!")
            print(f"{'='*60}\n")
            return True
        finally:
            if protected_restore and protected_state is not None:
                print("\nRestoring protected restore settings...")
                self._disable_protected_restore(protected_state)
                print("✓ Protected restore settings restored")

            if restart_after_restore:
                print("\nApplying final safety reset: restarting MariaDB service...")
                self._restart_mariadb_service()

    def configure_settings(self):
        """Interactive configuration menu"""
        print(f"\n{'='*60}")
        print("Configuration Settings")
        print(f"{'='*60}")
        print(f"Config file: {os.path.abspath(self.config_file)}")
        print(f"{'='*60}\n")

        while True:
            print("\n1. MySQL Connection Settings")
            print("2. Backup Paths")
            print("3. Backup Options")
            print("4. Backup Rotation Settings")
            print("5. Webhook Settings")
            print("6. Replication Settings (Master for Slave)")
            print("7. Test MySQL Connection")
            print("8. View Current Configuration")
            print("9. Save and Exit")
            print("0. Exit without saving")

            choice = input("\nSelect option: ").strip()

            if choice == "1":
                print("\n--- MySQL Connection Settings ---")
                host = input(f"Host [{self.config['mysql']['host']}]: ").strip()
                if host:
                    self.config.set('mysql', 'host', host)
                    print(f"  → Set host to: {host}")
                
                port = input(f"Port [{self.config['mysql']['port']}]: ").strip()
                if port:
                    self.config.set('mysql', 'port', port)
                    print(f"  → Set port to: {port}")
                
                user = input(f"User [{self.config['mysql']['user']}]: ").strip()
                if user:
                    self.config.set('mysql', 'user', user)
                    print(f"  → Set user to: {user}")
                
                password = getpass.getpass("Password (leave empty to keep current): ")
                if password:
                    self.config.set('mysql', 'password', password)
                    print(f"  → Password updated")
                
                print(f"\n✓ Settings updated in memory (not saved yet)")


            elif choice == "2":
                print("\n--- Backup Paths ---")
                hourly = input(f"Hourly [{self.config['backup_paths']['hourly']}]: ").strip()
                if hourly:
                    self.config.set('backup_paths', 'hourly', hourly)
                
                daily = input(f"Daily [{self.config['backup_paths']['daily']}]: ").strip()
                if daily:
                    self.config.set('backup_paths', 'daily', daily)
                
                monthly = input(f"Monthly [{self.config['backup_paths']['monthly']}]: ").strip()
                if monthly:
                    self.config.set('backup_paths', 'monthly', monthly)

            elif choice == "3":
                print("\n--- Backup Options ---")
                compression = input(
                    f"Enable compression (yes/no) [{self.config['options'].get('compression', 'yes')}]: "
                ).strip()
                if compression:
                    self.config.set('options', 'compression', compression)

            elif choice == "4":
                print("\n--- Backup Rotation Settings ---")
                print("Set how many backups to keep for each type (0 = unlimited)")
                
                hourly = input(f"Hourly backups to keep [{self.config['rotation'].get('hourly_keep', '24')}]: ").strip()
                if hourly:
                    self.config.set('rotation', 'hourly_keep', hourly)
                    print(f"  → Will keep last {hourly} hourly backups")
                
                daily = input(f"Daily backups to keep [{self.config['rotation'].get('daily_keep', '31')}]: ").strip()
                if daily:
                    self.config.set('rotation', 'daily_keep', daily)
                    print(f"  → Will keep last {daily} daily backups")
                
                monthly = input(f"Monthly backups to keep [{self.config['rotation'].get('monthly_keep', '12')}]: ").strip()
                if monthly:
                    self.config.set('rotation', 'monthly_keep', monthly)
                    print(f"  → Will keep last {monthly} monthly backups")
                
                print(f"\n✓ Rotation settings updated in memory (not saved yet)")

            elif choice == "5":
                print("\n--- Webhook Settings ---")
                current_success = self.config['webhooks'].get('success_url', '') if self.config.has_section('webhooks') else ''
                current_failure = self.config['webhooks'].get('failure_url', '') if self.config.has_section('webhooks') else ''
                success = input(f"Success webhook URL [{current_success}]: ").strip()
                if success:
                    if not self.config.has_section('webhooks'):
                        self.config.add_section('webhooks')
                    self.config.set('webhooks', 'success_url', success)
                    print(f"  → Success webhook set")
                failure = input(f"Failure webhook URL [{current_failure}]: ").strip()
                if failure:
                    if not self.config.has_section('webhooks'):
                        self.config.add_section('webhooks')
                    self.config.set('webhooks', 'failure_url', failure)
                    print(f"  → Failure webhook set")
                print("\n✓ Webhook settings updated in memory (not saved yet)")

            elif choice == "6":
                print("\n--- Replication Settings (Master for Slave) ---")
                print("Configure master server details for slave replication.")
                print("Leave empty if this server is standalone or will be a master.\n")
                
                if not self.config.has_section('replication'):
                    self.config.add_section('replication')
                
                current_host = self.config['replication'].get('master_host', '')
                current_user = self.config['replication'].get('master_user', '')
                current_pass = self.config['replication'].get('master_password', '')
                current_port = self.config['replication'].get('master_port', '3306')
                
                master_host = input(f"Master Host/IP [{current_host}]: ").strip()
                if master_host:
                    self.config.set('replication', 'master_host', master_host)
                    print(f"  → Master host set to: {master_host}")
                
                master_user = input(f"Master Replication User [{current_user}]: ").strip()
                if master_user:
                    self.config.set('replication', 'master_user', master_user)
                    print(f"  → Master user set to: {master_user}")
                
                master_pass = getpass.getpass(f"Master Password [{'*' * len(current_pass) if current_pass else 'empty'}]: ")
                if master_pass:
                    self.config.set('replication', 'master_password', master_pass)
                    print(f"  → Master password set")
                
                master_port = input(f"Master Port [{current_port}]: ").strip()
                if master_port:
                    self.config.set('replication', 'master_port', master_port)
                    print(f"  → Master port set to: {master_port}")
                
                print("\n✓ Replication settings updated in memory (not saved yet)")
                print("   These will be used when restoring as a slave.")

            elif choice == "7":
                print("\nTesting MySQL connection...")
                print(f"  Host: {self.config['mysql']['host']}")
                print(f"  Port: {self.config['mysql']['port']}")
                print(f"  User: {self.config['mysql']['user']}")
                print(f"  Password: {'*' * len(self.config['mysql'].get('password', '')) if self.config['mysql'].get('password') else '(empty)'}")
                print()
                if self.test_connection():
                    print("✓ Connection successful!")
                else:
                    print("✗ Connection failed! Check your settings.")
                    print("\nTip: Test manually with:")
                    print(f"  mysql --host={self.config['mysql']['host']} --port={self.config['mysql']['port']} --user={self.config['mysql']['user']} -p")

            elif choice == "8":
                print("\n--- Current Configuration ---")
                print(f"Config file: {os.path.abspath(self.config_file)}")
                print(f"File exists: {os.path.exists(self.config_file)}")
                if os.path.exists(self.config_file):
                    print(f"File size: {os.path.getsize(self.config_file)} bytes")
                    mtime = os.path.getmtime(self.config_file)
                    print(f"Last modified: {datetime.datetime.fromtimestamp(mtime)}")
                
                print(f"\n[mysql]")
                print(f"  host = {self.config['mysql']['host']}")
                print(f"  port = {self.config['mysql']['port']}")
                print(f"  user = {self.config['mysql']['user']}")
                pwd = self.config['mysql'].get('password', '')
                print(f"  password = {'*' * len(pwd) if pwd else '(empty)'}")
                print(f"\n[backup_paths]")
                print(f"  hourly = {self.config['backup_paths']['hourly']}")
                print(f"  daily = {self.config['backup_paths']['daily']}")
                print(f"  monthly = {self.config['backup_paths']['monthly']}")
                print(f"\n[options]")
                print(f"  compression = {self.config['options'].get('compression', 'yes')}")
                print(f"\n[rotation]")
                print(f"  hourly_keep = {self.config['rotation'].get('hourly_keep', '24')}")
                print(f"  daily_keep = {self.config['rotation'].get('daily_keep', '31')}")
                print(f"  monthly_keep = {self.config['rotation'].get('monthly_keep', '12')}")
                if self.config.has_section('replication'):
                    print(f"\n[replication]")
                    master_host = self.config['replication'].get('master_host', '')
                    master_user = self.config['replication'].get('master_user', '')
                    master_pass = self.config['replication'].get('master_password', '')
                    master_port = self.config['replication'].get('master_port', '3306')
                    print(f"  master_host = {master_host if master_host else '(not set)'}")
                    print(f"  master_user = {master_user if master_user else '(not set)'}")
                    print(f"  master_password = {'*' * len(master_pass) if master_pass else '(not set)'}")
                    print(f"  master_port = {master_port}")
                if self.config.has_section('webhooks'):
                    print(f"\n[webhooks]")
                    print(f"  success_url = {self.config['webhooks'].get('success_url', '')}")
                    print(f"  failure_url = {self.config['webhooks'].get('failure_url', '')}")
                
                print(f"\nPress Enter to continue...")
                input()

            elif choice == "9":
                if self.save_config():
                    print(f"\n✓ Configuration saved to {self.config_file}!")
                    print(f"  File size: {os.path.getsize(self.config_file)} bytes")
                    # Reload config to ensure consistency
                    self.config = self.load_config()
                else:
                    print(f"\n✗ Error saving configuration to {self.config_file}")
                break

            elif choice == "0":
                print("\nExiting without saving.")
                break

    def manage_schedule(self):
        """Manage automated backup schedule (cron)"""
        print(f"\n{'='*60}")
        print("Backup Schedule Management")
        print(f"{'='*60}\n")
        
        # Get current crontab
        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            current_cron = result.stdout if result.returncode == 0 else ""
        except Exception as e:
            print(f"ERROR: Could not read crontab: {e}")
            return
        
        # Check for existing MariaDB backup entries
        mariadb_entries = []
        other_entries = []
        
        for line in current_cron.split('\n'):
            if 'mariadb_manager.py' in line or 'MariaDB' in line:
                mariadb_entries.append(line)
            elif line.strip():
                other_entries.append(line)
        
        if mariadb_entries:
            print("Current MariaDB backup schedule:")
            print("-" * 60)
            for entry in mariadb_entries:
                print(entry)
            print("-" * 60)
            print()
        else:
            print("No automated backups currently scheduled.")
            print()
        
        print("Options:")
        print("  1. Add/Update schedule")
        print("  2. Remove all MariaDB backup schedules")
        print("  3. View full crontab")
        print("  0. Back to main menu")
        
        choice = input("\nSelect option: ").strip()
        
        if choice == "1":
            print("\nSelect backup schedule:")
            print("  1. Hourly + Daily + Monthly (recommended)")
            print("  2. Daily only")
            print("  3. Daily + Monthly")
            print("  4. Custom")
            
            schedule_choice = input("\nOption (1-4): ").strip()
            
            script_path = os.path.abspath(sys.argv[0])
            config_path = os.path.abspath(self.config_file)
            
            new_entries = []
            
            if schedule_choice == "1":
                new_entries = [
                    "# MariaDB Hourly Backup",
                    f"0 * * * * {script_path} --backup hourly --config {config_path} >> /var/log/mariadb_backup.log 2>&1",
                    "",
                    "# MariaDB Daily Backup (2 AM)",
                    f"0 2 * * * {script_path} --backup daily --config {config_path} >> /var/log/mariadb_backup.log 2>&1",
                    "",
                    "# MariaDB Monthly Backup (1st of month, 3 AM)",
                    f"0 3 1 * * {script_path} --backup monthly --config {config_path} >> /var/log/mariadb_backup.log 2>&1"
                ]
            elif schedule_choice == "2":
                new_entries = [
                    "# MariaDB Daily Backup (2 AM)",
                    f"0 2 * * * {script_path} --backup daily --config {config_path} >> /var/log/mariadb_backup.log 2>&1"
                ]
            elif schedule_choice == "3":
                new_entries = [
                    "# MariaDB Daily Backup (2 AM)",
                    f"0 2 * * * {script_path} --backup daily --config {config_path} >> /var/log/mariadb_backup.log 2>&1",
                    "",
                    "# MariaDB Monthly Backup (1st of month, 3 AM)",
                    f"0 3 1 * * {script_path} --backup monthly --config {config_path} >> /var/log/mariadb_backup.log 2>&1"
                ]
            elif schedule_choice == "4":
                print("\nCustom schedule:")
                print("Enter cron schedule (e.g., '0 2 * * *' for daily at 2 AM)")
                print("Leave empty to skip each type")
                print()
                
                hourly_sched = input("Hourly schedule (e.g., '0 * * * *'): ").strip()
                if hourly_sched:
                    new_entries.extend([
                        "# MariaDB Hourly Backup",
                        f"{hourly_sched} {script_path} --backup hourly --config {config_path} >> /var/log/mariadb_backup.log 2>&1",
                        ""
                    ])
                
                daily_sched = input("Daily schedule (e.g., '0 2 * * *'): ").strip()
                if daily_sched:
                    new_entries.extend([
                        "# MariaDB Daily Backup",
                        f"{daily_sched} {script_path} --backup daily --config {config_path} >> /var/log/mariadb_backup.log 2>&1",
                        ""
                    ])
                
                monthly_sched = input("Monthly schedule (e.g., '0 3 1 * *'): ").strip()
                if monthly_sched:
                    new_entries.extend([
                        "# MariaDB Monthly Backup",
                        f"{monthly_sched} {script_path} --backup monthly --config {config_path} >> /var/log/mariadb_backup.log 2>&1"
                    ])
            else:
                print("Invalid option")
                return
            
            if new_entries:
                print("\n" + "="*60)
                print("New schedule to be added:")
                print("-" * 60)
                for entry in new_entries:
                    print(entry)
                print("-" * 60)
                
                confirm = input("\nApply this schedule? (yes/no): ").strip().lower()
                
                if confirm == "yes":
                    # Build new crontab: other entries + new MariaDB entries
                    new_cron_lines = other_entries + [''] + new_entries
                    new_cron = '\n'.join(new_cron_lines) + '\n'
                    
                    try:
                        proc = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
                        proc.communicate(input=new_cron)
                        
                        if proc.returncode == 0:
                            print("\n✓ Schedule updated successfully!")
                            print("\nView schedule with: crontab -l")
                            print("View logs with: tail -f /var/log/mariadb_backup.log")
                        else:
                            print("\n✗ Failed to update crontab")
                    except Exception as e:
                        print(f"\n✗ Error updating crontab: {e}")
                else:
                    print("\nCancelled.")
        
        elif choice == "2":
            if not mariadb_entries:
                print("\nNo MariaDB backup schedules to remove.")
                return
            
            confirm = input("\nRemove all MariaDB backup schedules? (yes/no): ").strip().lower()
            
            if confirm == "yes":
                # Keep only non-MariaDB entries
                new_cron = '\n'.join(other_entries) + '\n' if other_entries else ''
                
                try:
                    proc = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
                    proc.communicate(input=new_cron)
                    
                    if proc.returncode == 0:
                        print("\n✓ All MariaDB backup schedules removed")
                    else:
                        print("\n✗ Failed to update crontab")
                except Exception as e:
                    print(f"\n✗ Error updating crontab: {e}")
            else:
                print("\nCancelled.")
        
        elif choice == "3":
            print("\nFull crontab:")
            print("=" * 60)
            print(current_cron if current_cron else "(empty)")
            print("=" * 60)
            input("\nPress Enter to continue...")

    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            print(f"\n{'='*60}")
            print("MariaDB Backup & Restore Manager")
            print(f"{'='*60}")
            print(f"Config: {os.path.abspath(self.config_file)}")
            print(f"{'='*60}")
            print("\nBACKUP OPTIONS:")
            print("  1. Create Hourly Backup")
            print("  2. Create Daily Backup")
            print("  3. Create Monthly Backup")
            print("  4. Create Manual Backup")
            print("\nRESTORE OPTIONS:")
            print("  5. List Available Backups")
            print("  6. Restore Backup (Standalone/Master)")
            print("  7. Restore Backup as Slave (with replication)")
            print("\nSETTINGS:")
            print("  8. Configure Settings")
            print("  9. Test MySQL Connection")
            print(" 10. Manage Backup Schedule (cron)")
            print("\nDISASTER RECOVERY:")
            print(" 11. Disaster Recovery Mode (fix server + configure restore access)")
            print("\n  0. Exit")

            choice = input("\nSelect option: ").strip()

            if choice == "1":
                self.backup_databases("hourly")
            elif choice == "2":
                self.backup_databases("daily")
            elif choice == "3":
                self.backup_databases("monthly")
            elif choice == "4":
                backup_path = input(
                    "Enter backup path (or press Enter for default): "
                ).strip()
                self.backup_databases("manual", backup_path if backup_path else None)

            elif choice == "5":
                # Prompt for backup type
                print("\nSelect backup type:")
                print("  1. Hourly")
                print("  2. Daily")
                print("  3. Monthly")
                print("  4. All")
                type_choice = input("\nSelect type: ").strip()
                
                type_map = {"1": "hourly", "2": "daily", "3": "monthly", "4": None}
                backup_type = type_map.get(type_choice)
                
                if type_choice in type_map:
                    self.list_backups(backup_type)
                else:
                    print("Invalid selection")

            elif choice == "6":
                # Prompt for backup type
                print("\nSelect backup type:")
                print("  1. Hourly")
                print("  2. Daily")
                print("  3. Monthly")
                print("  4. All")
                type_choice = input("\nSelect type: ").strip()
                
                type_map = {"1": "hourly", "2": "daily", "3": "monthly", "4": None}
                backup_type = type_map.get(type_choice)
                
                if type_choice in type_map:
                    backups = self.list_backups(backup_type)
                    if backups:
                        try:
                            idx = int(input("\nEnter backup number to restore: ")) - 1
                            if 0 <= idx < len(backups):
                                print("\nSelect restore mode:")
                                print("  1. full (databases + users/grants)")
                                print("  2. users-grants (users/grants only)")
                                print("  3. databases (schema + data + routines/functions/events/triggers/sequences)")
                                print("  4. schema (objects only; no row data)")
                                print("  5. data (row data only)")
                                mode_choice = input("\nSelect mode [1]: ").strip() or "1"
                                mode_map = {
                                    "1": "full",
                                    "2": "users-grants",
                                    "3": "databases",
                                    "4": "schema",
                                    "5": "data",
                                }
                                restore_mode = mode_map.get(mode_choice)
                                if not restore_mode:
                                    print("Invalid restore mode")
                                    continue

                                protected_choice = input("Use protected restore mode? (yes/no) [yes]: ").strip().lower()
                                protected_restore = protected_choice in {"", "y", "yes"}
                                drop_choice = input("Drop non-system databases before restore? (yes/no) [no]: ").strip().lower()
                                drop_non_system = drop_choice in {"y", "yes"}

                                self.restore_backup(
                                    backups[idx]["path"],
                                    restore_mode=restore_mode,
                                    protected_restore=protected_restore,
                                    drop_non_system_databases=drop_non_system,
                                )
                            else:
                                print("Invalid backup number")
                        except ValueError:
                            print("Invalid input")
                else:
                    print("Invalid selection")

            elif choice == "7":
                # Prompt for backup type
                print("\nSelect backup type:")
                print("  1. Hourly")
                print("  2. Daily")
                print("  3. Monthly")
                print("  4. All")
                type_choice = input("\nSelect type: ").strip()
                
                type_map = {"1": "hourly", "2": "daily", "3": "monthly", "4": None}
                backup_type = type_map.get(type_choice)
                
                if type_choice in type_map:
                    backups = self.list_backups(backup_type)
                    if backups:
                        try:
                            idx = int(input("\nEnter backup number to restore: ")) - 1
                            if 0 <= idx < len(backups):
                                print("\nSelect restore mode:")
                                print("  1. full (databases + users/grants)")
                                print("  2. users-grants (users/grants only)")
                                print("  3. databases (schema + data + routines/functions/events/triggers/sequences)")
                                print("  4. schema (objects only; no row data)")
                                print("  5. data (row data only)")
                                mode_choice = input("\nSelect mode [1]: ").strip() or "1"
                                mode_map = {
                                    "1": "full",
                                    "2": "users-grants",
                                    "3": "databases",
                                    "4": "schema",
                                    "5": "data",
                                }
                                restore_mode = mode_map.get(mode_choice)
                                if not restore_mode:
                                    print("Invalid restore mode")
                                    continue

                                protected_choice = input("Use protected restore mode? (yes/no) [yes]: ").strip().lower()
                                protected_restore = protected_choice in {"", "y", "yes"}
                                drop_choice = input("Drop non-system databases before restore? (yes/no) [no]: ").strip().lower()
                                drop_non_system = drop_choice in {"y", "yes"}

                                # Check if config has replication settings
                                has_config = self.config.has_section('replication')
                                config_host = self.config['replication'].get('master_host', '') if has_config else ''
                                config_user = self.config['replication'].get('master_user', '') if has_config else ''
                                config_pass = self.config['replication'].get('master_password', '') if has_config else ''
                                config_port = self.config['replication'].get('master_port', '3306') if has_config else '3306'
                                
                                if config_host and config_user and config_pass:
                                    print("\n📋 Found saved replication settings in config:")
                                    print(f"   Master: {config_host}:{config_port}")
                                    print(f"   User: {config_user}")
                                    use_config = input("\nUse saved settings? (yes/no) [yes]: ").strip().lower()
                                    
                                    if use_config in ['', 'y', 'yes']:
                                        # Use config settings
                                        master_host = None
                                        master_user = None
                                        master_password = None
                                        master_port = None
                                    else:
                                        # Prompt for manual input
                                        master_host = input(f"Master host/IP [{config_host}]: ").strip() or None
                                        master_user = input(f"Master replication user [{config_user}]: ").strip() or None
                                        master_password = getpass.getpass("Master replication password: ") or None
                                        master_port = input(f"Master port [{config_port}]: ").strip() or None
                                else:
                                    # No config or incomplete config, prompt for input
                                    print("\n⚠️  No saved replication settings found in config.")
                                    print("   You can configure these in Settings menu (option 8).\n")
                                    master_host = input("Master host/IP: ").strip() or None
                                    master_user = input("Master replication user: ").strip() or None
                                    master_password = getpass.getpass("Master replication password: ") or None
                                    master_port = input("Master port [3306]: ").strip() or None

                                self.restore_backup(
                                    backups[idx]["path"],
                                    restore_as_slave=True,
                                    master_host=master_host,
                                    master_user=master_user,
                                    master_password=master_password,
                                    master_port=master_port,
                                    restore_mode=restore_mode,
                                    protected_restore=protected_restore,
                                    drop_non_system_databases=drop_non_system,
                                )
                            else:
                                print("Invalid backup number")
                        except ValueError:
                            print("Invalid input")
                else:
                    print("Invalid selection")

            elif choice == "8":
                self.configure_settings()

            elif choice == "9":
                print("\nTesting MySQL connection...")
                if self.test_connection():
                    print("✓ Connection successful!")
                else:
                    print("✗ Connection failed! Check your settings.")

            elif choice == "10":
                self.manage_schedule()

            elif choice == "11":
                reset_choice = input(
                    "Reset mysql system tables if needed? (yes/no) [no]: "
                ).strip().lower()
                reset_system_tables = reset_choice in {"y", "yes"}
                restore_path = input(
                    "Restore from backup path after recovery (optional): "
                ).strip()
                self.disaster_recovery(
                    reset_system_tables=reset_system_tables,
                    restore_path=restore_path if restore_path else None,
                )

            elif choice == "0":
                print("\nExiting...")
                break

            else:
                print("Invalid option")


def main():
    parser = argparse.ArgumentParser(
        description="MariaDB Backup and Restore Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive menu
  %(prog)s
  
  # Create backups (for cron)
  %(prog)s --backup hourly
  %(prog)s --backup daily
  %(prog)s --backup monthly
  %(prog)s --backup manual --path /custom/path
  
  # List backups
  %(prog)s --list
  %(prog)s --list --type daily
  
  # Restore as master/standalone
  %(prog)s --restore /path/to/backup

    # Restore without protection mode (not recommended)
    %(prog)s --restore /path/to/backup --unprotected-restore

    # Destructive restore prep: drop non-system databases first
    %(prog)s --restore /path/to/backup --drop-non-system-databases

    # Skip automatic post-restore service restart
    %(prog)s --restore /path/to/backup --no-restart-after-restore

    # Restore users and grants only
    %(prog)s --restore /path/to/backup --restore-mode users-grants

    # Restore DB schema objects only (tables/views/procs/functions/events/triggers/sequences)
    %(prog)s --restore /path/to/backup --restore-mode schema
  
  # Restore as slave (with config file settings)
  %(prog)s --restore /path/to/backup --slave
  
  # Restore as slave (with explicit master settings)
  %(prog)s --restore /path/to/backup --slave \\
           --master-host 192.168.1.100 \\
           --master-user repl_user \\
           --master-password secret \\
           --master-port 3306

  # Disaster recovery when MariaDB will not start
  sudo %(prog)s --disaster-recovery --dr-admin-pass 'StrongPass123!'
  sudo %(prog)s --disaster-recovery --reset-mysql-system-tables --dr-admin-pass 'StrongPass123!'
  sudo %(prog)s --disaster-recovery --dr-admin-pass 'StrongPass123!' \\
      --restore /path/to/backup --restore-mode full
  
  # Configuration
  %(prog)s --config /path/to/config.conf
        """,
    )

    parser.add_argument(
        "--config", "-c", default=None, 
        help="Configuration file path (default: auto-detect from /etc, ~/.config, or current directory)"
    )
    parser.add_argument(
        "--backup",
        "-b",
        choices=["hourly", "daily", "monthly", "manual"],
        help="Create backup",
    )
    parser.add_argument("--path", "-p", help="Custom backup path (for manual backup)")
    parser.add_argument(
        "--list", "-l", action="store_true", help="List available backups"
    )
    parser.add_argument(
        "--type",
        "-t",
        choices=["hourly", "daily", "monthly"],
        help="Filter backups by type (with --list)",
    )
    parser.add_argument(
        "--restore", "-r", metavar="PATH", help="Restore backup from path"
    )
    parser.add_argument(
        "--restore-mode",
        choices=["full", "users-grants", "databases", "schema", "data"],
        default="full",
        help="Restore scope: full, users-grants, databases, schema, or data (default: full)",
    )
    parser.add_argument(
        "--unprotected-restore",
        action="store_true",
        help="Disable protected restore mode (default keeps server read-only and event scheduler off during restore)",
    )
    parser.add_argument(
        "--drop-non-system-databases",
        action="store_true",
        help="Drop all non-system databases before restore (destructive)",
    )
    parser.add_argument(
        "--no-restart-after-restore",
        action="store_true",
        help="Do not restart MariaDB service after restore (default is to restart for safety)",
    )
    parser.add_argument(
        "--slave", "-s", action="store_true", help="Configure as slave (with --restore)"
    )
    parser.add_argument("--master-host", help="Master host for slave setup")
    parser.add_argument("--master-user", help="Master replication user")
    parser.add_argument("--master-password", help="Master replication password")
    parser.add_argument("--master-port", help="Master port for slave setup (default: 3306)")
    parser.add_argument(
        "--disaster-recovery",
        action="store_true",
        help="Run disaster recovery workflow (diagnose, optionally reset mysql system tables, configure restore access)",
    )
    parser.add_argument(
        "--reset-mysql-system-tables",
        action="store_true",
        help="With --disaster-recovery: reset mysql system schema files and reinitialize system tables",
    )
    parser.add_argument(
        "--dr-admin-user",
        default=None,
        help="Restore admin user for disaster recovery (default: config user or restore_admin)",
    )
    parser.add_argument(
        "--dr-admin-pass",
        default=None,
        help="Restore admin password for disaster recovery (required for non-interactive mode)",
    )
    parser.add_argument(
        "--dr-admin-host",
        default="localhost",
        help="Host part for restore admin user (default: localhost)",
    )
    parser.add_argument(
        "--dr-root-pass",
        default=None,
        help="Optional new MariaDB root@localhost password during disaster recovery",
    )
    parser.add_argument(
        "--dr-yes",
        action="store_true",
        help="Skip disaster recovery confirmation prompts",
    )

    args = parser.parse_args()

    # Create manager instance
    manager = MariaDBManager(args.config)

    # Handle command line mode
    if args.backup:
        success = manager.backup_databases(args.backup, args.path)
        sys.exit(0 if success else 1)

    elif args.list:
        manager.list_backups(args.type)
        sys.exit(0)

    elif args.disaster_recovery:
        success = manager.disaster_recovery(
            reset_system_tables=args.reset_mysql_system_tables,
            admin_user=args.dr_admin_user,
            admin_password=args.dr_admin_pass,
            admin_host=args.dr_admin_host,
            root_password=args.dr_root_pass,
            skip_confirm=args.dr_yes,
            restore_path=args.restore,
            restore_as_slave=args.slave,
            restore_mode=args.restore_mode,
            protected_restore=not args.unprotected_restore,
            drop_non_system_databases=args.drop_non_system_databases,
            restart_after_restore=not args.no_restart_after_restore,
        )
        sys.exit(0 if success else 1)

    elif args.restore:
        success = manager.restore_backup(
            args.restore,
            restore_as_slave=args.slave,
            master_host=args.master_host,
            master_user=args.master_user,
            master_password=args.master_password,
            master_port=args.master_port if hasattr(args, 'master_port') else None,
            restore_mode=args.restore_mode,
            protected_restore=not args.unprotected_restore,
            drop_non_system_databases=args.drop_non_system_databases,
            restart_after_restore=not args.no_restart_after_restore,
        )
        sys.exit(0 if success else 1)

    else:
        # Interactive menu mode
        try:
            manager.interactive_menu()
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            sys.exit(0)


if __name__ == "__main__":
    main()
