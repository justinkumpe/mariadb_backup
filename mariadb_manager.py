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
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


class MariaDBManager:
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
            # Check if required config values are present
            if not self.config.get('mysql', 'password', fallback=''):
                print("WARNING: MySQL password is empty")
            
            cmd = ["mysql"] + self.get_mysql_connection_args() + ["-e", "SELECT 1;"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"Connection error: {result.stderr}")
                
            return result.returncode == 0
        except Exception as e:
            print(f"Connection test failed: {e}")
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
                    mysqldump_cmd, stdout=f, stderr=subprocess.PIPE, text=True
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
            result = subprocess.run(get_users_cmd, capture_output=True, text=True)

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
                for item in os.listdir(path):
                    item_path = os.path.join(path, item)
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

        if not all_backups:
            print("No backups found.")
            return []

        # Sort by modification time (newest first)
        all_backups.sort(key=lambda x: x["mtime"], reverse=True)

        for idx, backup in enumerate(all_backups, 1):
            backup_time = datetime.datetime.fromtimestamp(backup["mtime"])
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
        master_port=None,
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
                # Stop slave if running and reset any existing configuration
                print("  → Stopping any existing slave processes...")
                cmd = (
                    ["mysql"] + self.get_mysql_connection_args() + ["-e", "STOP SLAVE;"]
                )
                subprocess.run(cmd, capture_output=True)

                print("  → Resetting slave configuration...")
                cmd = (
                    ["mysql"] + self.get_mysql_connection_args() + ["-e", "RESET SLAVE ALL;"]
                )
                subprocess.run(cmd, capture_output=True)

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
                result = subprocess.run(cmd, capture_output=True, text=True)

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
                result = subprocess.run(cmd, capture_output=True, text=True)

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

            elif choice == "10":
                self.manage_schedule()

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
  
  # Restore as slave (with config file settings)
  %(prog)s --restore /path/to/backup --slave
  
  # Restore as slave (with explicit master settings)
  %(prog)s --restore /path/to/backup --slave \\
           --master-host 192.168.1.100 \\
           --master-user repl_user \\
           --master-password secret \\
           --master-port 3306
  
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
        "--slave", "-s", action="store_true", help="Configure as slave (with --restore)"
    )
    parser.add_argument("--master-host", help="Master host for slave setup")
    parser.add_argument("--master-user", help="Master replication user")
    parser.add_argument("--master-password", help="Master replication password")
    parser.add_argument("--master-port", help="Master port for slave setup (default: 3306)")

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
        success = manager.restore_backup(
            args.restore,
            restore_as_slave=args.slave,
            master_host=args.master_host,
            master_user=args.master_user,
            master_password=args.master_password,
            master_port=args.master_port if hasattr(args, 'master_port') else None,
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
