#!/usr/bin/env python3

"""
MariaDB Backup and Restore Manager
Comprehensive solution for backing up and restoring MariaDB databases
with support for master/slave replication configuration.
"""

import argparse
import configparser
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import shutil
import getpass


class MariaDBManager:
    def __init__(self, config_file="mariadb_backup.conf"):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        """Load configuration from file or create default"""
        config = configparser.ConfigParser()

        if os.path.exists(self.config_file):
            config.read(self.config_file)
        else:
            # Create default configuration
            config["mysql"] = {
                "host": "localhost",
                "user": "root",
                "password": "",
                "port": "3306",
            }
            config["backup_paths"] = {
                "hourly": "/var/backups/mariadb/hourly",
                "daily": "/var/backups/mariadb/daily",
                "monthly": "/var/backups/mariadb/monthly",
            }
            config["options"] = {
                "compression": "yes",
                "encryption": "no",
                "encryption_key_file": "/root/.mariadb_backup_key",
            }

            self.save_config(config)
            print(f"Default configuration created at {self.config_file}")
            print("Please edit the configuration file with your MySQL credentials.")

        return config

    def save_config(self, config=None):
        """Save configuration to file"""
        if config is None:
            config = self.config

        with open(self.config_file, "w") as f:
            config.write(f)
        os.chmod(self.config_file, 0o600)

    def get_mysql_connection_args(self):
        """Get MySQL connection arguments"""
        return [
            f"--host={self.config['mysql']['host']}",
            f"--user={self.config['mysql']['user']}",
            f"--password={self.config['mysql']['password']}",
            f"--port={self.config['mysql']['port']}",
        ]

    def test_connection(self):
        """Test MySQL connection"""
        try:
            cmd = ["mysql"] + self.get_mysql_connection_args() + ["-e", "SELECT 1;"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

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
        now = datetime.now()
        if backup_type == "hourly":
            # Same hour overwrites: YYYYMMDD_HH
            backup_name = now.strftime("%Y%m%d_%H")
        elif backup_type == "daily":
            # Same day overwrites: YYYYMMDD
            backup_name = now.strftime("%Y%m%d")
        elif backup_type == "monthly":
            # Same month overwrites: YYYYMM
            backup_name = now.strftime("%Y%m")
        else:
            # Manual/other: full timestamp
            backup_name = now.strftime("%Y%m%d_%H%M%S")

        backup_dir = os.path.join(base_dir, f"backup_{backup_name}")

        # Remove existing backup if it exists (for overwrite behavior)
        if os.path.exists(backup_dir):
            print(f"Removing existing backup: {backup_dir}")
            shutil.rmtree(backup_dir)

        os.makedirs(backup_dir, exist_ok=True)

        print(f"Backup directory: {backup_dir}")

        # Test connection
        if not self.test_connection():
            print("ERROR: Cannot connect to MySQL. Check your credentials.")
            return False

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
                    mysqldump_cmd, stdout=f, stderr=subprocess.PIPE, text=True
                )

            if result.returncode != 0:
                print(f"ERROR: Database backup failed: {result.stderr}")
                return False

            print(
                f"✓ Database backup completed: {os.path.getsize(db_backup_file)} bytes"
            )
        except Exception as e:
            print(f"ERROR: Database backup failed: {e}")
            return False

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
            result = subprocess.run(get_users_cmd, capture_output=True, text=True)

            with open(users_file, "w") as f:
                f.write("-- Users and Grants Backup\n")
                f.write(f"-- Created: {datetime.now()}\n\n")

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
                                show_create_cmd, capture_output=True, text=True
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
                                show_grants_cmd, capture_output=True, text=True
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
            result = subprocess.run(cmd, capture_output=True, text=True)
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
            result = subprocess.run(cmd, capture_output=True, text=True)
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

        print(f"\n{'='*60}")
        print(f"Backup completed successfully!")
        print(f"Location: {backup_dir}")
        print(f"{'='*60}\n")

        return True

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
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path) and item.startswith("backup_"):
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

        if not all_backups:
            print("No backups found.")
            return []

        # Sort by modification time (newest first)
        all_backups.sort(key=lambda x: x["mtime"], reverse=True)

        for idx, backup in enumerate(all_backups, 1):
            backup_time = datetime.fromtimestamp(backup["mtime"])
            size = sum(
                os.path.getsize(os.path.join(backup["path"], f))
                for f in os.listdir(backup["path"])
                if os.path.isfile(os.path.join(backup["path"], f))
            )

            print(f"{idx}. [{backup['type'].upper()}] {backup['name']}")
            print(f"   Time: {backup_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Size: {size:,} bytes ({size/1024/1024:.2f} MB)")
            print(f"   Path: {backup['path']}")
            print()

        return all_backups

    def restore_backup(
        self,
        backup_path,
        restore_as_slave=False,
        master_host=None,
        master_user=None,
        master_password=None,
    ):
        """
        Restore a backup

        Args:
            backup_path: Path to backup directory
            restore_as_slave: Whether to configure as replication slave
            master_host: Master server hostname/IP (for slave setup)
            master_user: Master replication user (for slave setup)
            master_password: Master replication password (for slave setup)
        """
        print(f"\n{'='*60}")
        print(f"Restoring Backup")
        print(f"{'='*60}\n")

        if not os.path.exists(backup_path):
            print(f"ERROR: Backup path not found: {backup_path}")
            return False

        print(f"Backup location: {backup_path}")

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

        if restore_as_slave:
            print(f"   Mode: SLAVE (replication will be configured)")
            if not master_host:
                print(f"   ERROR: Master host required for slave setup")
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

        # 1. Restore databases
        print("\n[1/3] Restoring databases...")
        try:
            if is_compressed:
                # Decompress and pipe to mysql
                gunzip = subprocess.Popen(
                    ["gunzip", "-c", db_file], stdout=subprocess.PIPE
                )
                mysql = subprocess.Popen(
                    ["mysql"] + self.get_mysql_connection_args(),
                    stdin=gunzip.stdout,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                gunzip.stdout.close()
                _, stderr = mysql.communicate()

                if mysql.returncode != 0:
                    print(f"ERROR: Database restore failed: {stderr}")
                    return False
            else:
                # Direct restore
                with open(db_file, "r") as f:
                    mysql = subprocess.Popen(
                        ["mysql"] + self.get_mysql_connection_args(),
                        stdin=f,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    _, stderr = mysql.communicate()

                    if mysql.returncode != 0:
                        print(f"ERROR: Database restore failed: {stderr}")
                        return False

            print("✓ Databases restored successfully")
        except Exception as e:
            print(f"ERROR: Database restore failed: {e}")
            return False

        # 2. Restore users (optional)
        print("\n[2/3] Restoring users and grants...")

        if os.path.exists(users_gz):
            users_restore_file = users_gz
            is_users_compressed = True
        elif os.path.exists(users_file):
            users_restore_file = users_file
            is_users_compressed = False
        else:
            print("WARNING: Users backup file not found, skipping")
            users_restore_file = None

        if users_restore_file:
            try:
                if is_users_compressed:
                    gunzip = subprocess.Popen(
                        ["gunzip", "-c", users_restore_file], stdout=subprocess.PIPE
                    )
                    mysql = subprocess.Popen(
                        ["mysql"] + self.get_mysql_connection_args(),
                        stdin=gunzip.stdout,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    gunzip.stdout.close()
                    _, stderr = mysql.communicate()
                else:
                    with open(users_restore_file, "r") as f:
                        mysql = subprocess.Popen(
                            ["mysql"] + self.get_mysql_connection_args(),
                            stdin=f,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                        _, stderr = mysql.communicate()

                print("✓ Users and grants restored")
            except Exception as e:
                print(f"WARNING: Users restore had errors: {e}")

        # 3. Configure replication if requested
        if (
            restore_as_slave
            and replication_info
            and replication_info.get("master_status")
        ):
            print("\n[3/3] Configuring slave replication...")

            master_status = replication_info["master_status"]

            if not master_user or not master_password:
                print("ERROR: Master user and password required for slave setup")
                return False

            try:
                # Stop slave if running
                cmd = (
                    ["mysql"] + self.get_mysql_connection_args() + ["-e", "STOP SLAVE;"]
                )
                subprocess.run(cmd, capture_output=True)

                # Configure slave
                change_master_sql = f"""
                CHANGE MASTER TO
                    MASTER_HOST='{master_host}',
                    MASTER_USER='{master_user}',
                    MASTER_PASSWORD='{master_password}',
                    MASTER_PORT={self.config['mysql']['port']},
                    MASTER_LOG_FILE='{master_status['binlog_file']}',
                    MASTER_LOG_POS={master_status['binlog_position']};
                """

                cmd = (
                    ["mysql"]
                    + self.get_mysql_connection_args()
                    + ["-e", change_master_sql]
                )
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    print(f"ERROR: Failed to configure slave: {result.stderr}")
                    return False

                # Start slave
                cmd = (
                    ["mysql"]
                    + self.get_mysql_connection_args()
                    + ["-e", "START SLAVE;"]
                )
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    print(f"ERROR: Failed to start slave: {result.stderr}")
                    return False

                # Check slave status
                cmd = (
                    ["mysql"]
                    + self.get_mysql_connection_args()
                    + ["-e", "SHOW SLAVE STATUS\\G"]
                )
                result = subprocess.run(cmd, capture_output=True, text=True)

                print("✓ Slave replication configured")
                print("\nSlave Status:")
                print(result.stdout)

            except Exception as e:
                print(f"ERROR: Slave configuration failed: {e}")
                return False
        else:
            print("\n[3/3] Skipping replication configuration")

        print(f"\n{'='*60}")
        print("Restore completed successfully!")
        print(f"{'='*60}\n")

        return True

    def configure_settings(self):
        """Interactive configuration menu"""
        print(f"\n{'='*60}")
        print("Configuration Settings")
        print(f"{'='*60}\n")

        while True:
            print("\n1. MySQL Connection Settings")
            print("2. Backup Paths")
            print("3. Backup Options")
            print("4. Test MySQL Connection")
            print("5. Save and Exit")
            print("0. Exit without saving")

            choice = input("\nSelect option: ").strip()

            if choice == "1":
                print("\n--- MySQL Connection Settings ---")
                self.config["mysql"]["host"] = (
                    input(f"Host [{self.config['mysql']['host']}]: ").strip()
                    or self.config["mysql"]["host"]
                )
                self.config["mysql"]["port"] = (
                    input(f"Port [{self.config['mysql']['port']}]: ").strip()
                    or self.config["mysql"]["port"]
                )
                self.config["mysql"]["user"] = (
                    input(f"User [{self.config['mysql']['user']}]: ").strip()
                    or self.config["mysql"]["user"]
                )
                password = getpass.getpass("Password (leave empty to keep current): ")
                if password:
                    self.config["mysql"]["password"] = password

            elif choice == "2":
                print("\n--- Backup Paths ---")
                self.config["backup_paths"]["hourly"] = (
                    input(f"Hourly [{self.config['backup_paths']['hourly']}]: ").strip()
                    or self.config["backup_paths"]["hourly"]
                )
                self.config["backup_paths"]["daily"] = (
                    input(f"Daily [{self.config['backup_paths']['daily']}]: ").strip()
                    or self.config["backup_paths"]["daily"]
                )
                self.config["backup_paths"]["monthly"] = (
                    input(
                        f"Monthly [{self.config['backup_paths']['monthly']}]: "
                    ).strip()
                    or self.config["backup_paths"]["monthly"]
                )

            elif choice == "3":
                print("\n--- Backup Options ---")
                compression = input(
                    f"Enable compression (yes/no) [{self.config['options'].get('compression', 'yes')}]: "
                ).strip()
                if compression:
                    self.config["options"]["compression"] = compression

            elif choice == "4":
                print("\nTesting MySQL connection...")
                if self.test_connection():
                    print("✓ Connection successful!")
                else:
                    print("✗ Connection failed! Check your settings.")

            elif choice == "5":
                self.save_config()
                print("\n✓ Configuration saved!")
                break

            elif choice == "0":
                print("\nExiting without saving.")
                break

    def interactive_menu(self):
        """Main interactive menu"""
        while True:
            print(f"\n{'='*60}")
            print("MariaDB Backup & Restore Manager")
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
                self.list_backups()

            elif choice == "6":
                backups = self.list_backups()
                if backups:
                    try:
                        idx = int(input("\nEnter backup number to restore: ")) - 1
                        if 0 <= idx < len(backups):
                            self.restore_backup(backups[idx]["path"])
                        else:
                            print("Invalid backup number")
                    except ValueError:
                        print("Invalid input")

            elif choice == "7":
                backups = self.list_backups()
                if backups:
                    try:
                        idx = int(input("\nEnter backup number to restore: ")) - 1
                        if 0 <= idx < len(backups):
                            master_host = input("Master host/IP: ").strip()
                            master_user = input("Master replication user: ").strip()
                            master_password = getpass.getpass(
                                "Master replication password: "
                            )

                            self.restore_backup(
                                backups[idx]["path"],
                                restore_as_slave=True,
                                master_host=master_host,
                                master_user=master_user,
                                master_password=master_password,
                            )
                        else:
                            print("Invalid backup number")
                    except ValueError:
                        print("Invalid input")

            elif choice == "8":
                self.configure_settings()

            elif choice == "9":
                print("\nTesting MySQL connection...")
                if self.test_connection():
                    print("✓ Connection successful!")
                else:
                    print("✗ Connection failed! Check your settings.")

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
  
  # Restore as slave
  %(prog)s --restore /path/to/backup --slave \\
           --master-host 192.168.1.100 \\
           --master-user repl_user \\
           --master-password secret
  
  # Configuration
  %(prog)s --config /path/to/config.conf
        """,
    )

    parser.add_argument(
        "--config", "-c", default="mariadb_backup.conf", help="Configuration file path"
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
        "--slave", "-s", action="store_true", help="Configure as slave (with --restore)"
    )
    parser.add_argument("--master-host", help="Master host for slave setup")
    parser.add_argument("--master-user", help="Master replication user")
    parser.add_argument("--master-password", help="Master replication password")

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

    elif args.restore:
        if args.slave:
            if not args.master_host or not args.master_user or not args.master_password:
                print(
                    "ERROR: --master-host, --master-user, and --master-password required for slave setup"
                )
                sys.exit(1)

        success = manager.restore_backup(
            args.restore,
            restore_as_slave=args.slave,
            master_host=args.master_host,
            master_user=args.master_user,
            master_password=args.master_password,
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
