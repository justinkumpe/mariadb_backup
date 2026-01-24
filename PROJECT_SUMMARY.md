# MariaDB Backup Manager - Project Overview

## Complete Solution for MariaDB Backup & Restore

This is a comprehensive Python-based backup solution for MariaDB/MySQL with full replication support.

## Project Files

### Core Files

1. **mariadb_manager.py** (Main Script)
   - Python 3 script with interactive menu and CLI modes
   - Handles all backup and restore operations
   - Automatic slave replication configuration
   - ~1000 lines of production-ready code

2. **mariadb_backup.conf.example** (Configuration Template)
   - Sample configuration file
   - MySQL credentials and backup paths
   - Copy to `mariadb_backup.conf` and customize

### Installation & Testing

3. **install.sh** (Interactive Installer)
   - Guided installation process
   - System checks (Python, MySQL commands)
   - Configuration wizard
   - Cron job setup

4. **test_installation.py** (Verification Tool)
   - Tests all requirements
   - Validates configuration
   - Tests MySQL connection
   - Checks disk space

### Documentation

5. **README.md** (Complete Documentation)
   - Full feature list and usage guide
   - Installation instructions
   - Cron setup examples
   - Replication setup guide
   - Troubleshooting section

6. **QUICK_REFERENCE.md** (Cheat Sheet)
   - Common commands
   - One-liners
   - Quick troubleshooting
   - Performance tips

7. **SYSTEMD_TIMERS.md** (Systemd Alternative)
   - Systemd timer setup (alternative to cron)
   - Timer management commands
   - Advanced scheduling examples
   - Monitoring and logging

8. **PROJECT_SUMMARY.md** (This File)
   - Project overview
   - File descriptions
   - Quick start guide

### Supporting Files

9. **.gitignore**
   - Protects sensitive config files
   - Excludes backup directories
   - Standard Python ignores

10. **mariadb_backup.sh** (Original Script)
    - Your original bash script
    - Kept for reference
    - Superseded by Python solution

## Key Features

### Backup Features
- ✅ Complete database dumps with mysqldump
- ✅ All users and grants exported separately
- ✅ Binary log position captured for replication
- ✅ Hourly/Daily/Monthly backup types
- ✅ Automatic overwrite of same-period backups
- ✅ Compression support (gzip)
- ✅ Detailed manifests and metadata

### Restore Features
- ✅ Full database restoration
- ✅ User and grants restoration
- ✅ Restore as standalone/master
- ✅ **Automatic slave configuration** with replication
- ✅ Uses stored binary log position
- ✅ Interactive and command-line modes

### Operation Modes
- ✅ Interactive menu for human use
- ✅ Command-line for automation (cron)
- ✅ Configuration file or CLI arguments
- ✅ Separate paths for different backup types

### Replication Support
- ✅ Captures master status (binlog position)
- ✅ Stores replication metadata
- ✅ Automatic CHANGE MASTER TO configuration
- ✅ Automatic START SLAVE
- ✅ Replication status verification

## Quick Start

```bash
# 1. Make scripts executable
chmod +x *.py *.sh

# 2. Run installation (guided setup)
./install.sh

# 3. Or manual setup
cp mariadb_backup.conf.example mariadb_backup.conf
nano mariadb_backup.conf  # Edit MySQL credentials
chmod 600 mariadb_backup.conf

# 4. Test installation
./test_installation.py

# 5. Interactive menu
./mariadb_manager.py

# 6. Or command line
./mariadb_manager.py --backup daily
./mariadb_manager.py --list
./mariadb_manager.py --restore /path/to/backup
```

## Backup Types Explained

### Hourly Backups
- Filename format: `backup_YYYYMMDD_HH`
- Same hour overwrites previous
- Stores up to 24 backups (one per hour)
- Example: `backup_20260122_14` (Jan 22, 2026, 2 PM)

### Daily Backups
- Filename format: `backup_YYYYMMDD`
- Same day overwrites previous
- Stores up to 31 backups (one per day)
- Example: `backup_20260122` (Jan 22, 2026)

### Monthly Backups
- Filename format: `backup_YYYYMM`
- Same month overwrites previous
- Stores up to 12 backups (one per month)
- Example: `backup_202601` (January 2026)

### Manual Backups
- Filename format: `backup_YYYYMMDD_HHMMSS`
- Never overwrites (full timestamp)
- Stored in daily path by default or custom path
- Example: `backup_20260122_143025`

## Typical Workflows

### Setting Up Master-Slave Replication

**On Master:**
```bash
# 1. Configure master (enable binary logging)
# Edit /etc/mysql/mariadb.conf.d/50-server.cnf
[mysqld]
server-id = 1
log-bin = mysql-bin

# 2. Create replication user
mysql -e "CREATE USER 'repl'@'%' IDENTIFIED BY 'password'; \
          GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';"

# 3. Create backup
./mariadb_manager.py --backup daily
```

**On Slave:**
```bash
# 1. Configure slave (unique server-id)
# Edit /etc/mysql/mariadb.conf.d/50-server.cnf
[mysqld]
server-id = 2
read_only = 1

# 2. Restore as slave (automatic replication setup)
./mariadb_manager.py --restore /path/to/backup \
  --slave \
  --master-host 192.168.1.100 \
  --master-user repl \
  --master-password password

# 3. Verify replication
mysql -e "SHOW SLAVE STATUS\G"
```

### Scheduled Backups (Cron)

```bash
# Edit crontab
crontab -e

# Add lines:
0 * * * * /usr/local/bin/mariadb_manager.py --backup hourly
0 2 * * * /usr/local/bin/mariadb_manager.py --backup daily
0 3 1 * * /usr/local/bin/mariadb_manager.py --backup monthly
```

### Disaster Recovery

```bash
# 1. List available backups
./mariadb_manager.py --list

# 2. Select and restore
./mariadb_manager.py --restore /var/backups/mariadb/daily/backup_20260122

# 3. Verify
mysql -e "SHOW DATABASES;"
```

## Architecture

```
mariadb_manager.py
├── MariaDBManager (Main Class)
│   ├── load_config() - Read config file
│   ├── backup_databases() - Create backups
│   │   ├── mysqldump (all databases)
│   │   ├── Export users/grants
│   │   ├── Capture master status
│   │   └── Compress files
│   ├── restore_backup() - Restore from backup
│   │   ├── Restore databases
│   │   ├── Restore users/grants
│   │   └── Configure replication (if --slave)
│   ├── list_backups() - Show available backups
│   └── interactive_menu() - Menu-driven interface
└── main() - CLI argument parser
```

## Backup Structure

```
/var/backups/mariadb/
├── hourly/
│   ├── backup_20260122_14/
│   │   ├── all_databases.sql.gz
│   │   ├── users_and_grants.sql.gz
│   │   ├── replication_info.json
│   │   └── MANIFEST.txt
│   └── backup_20260122_15/
├── daily/
│   └── backup_20260122/
└── monthly/
    └── backup_202601/
```

## Configuration Structure

```ini
[mysql]
host = localhost          # MySQL server
user = root              # MySQL user
password = secret        # MySQL password
port = 3306             # MySQL port

[backup_paths]
hourly = /path/hourly   # Hourly backups
daily = /path/daily     # Daily backups
monthly = /path/monthly # Monthly backups

[options]
compression = yes       # Enable gzip compression
```

## System Requirements

- **Python**: 3.6 or higher
- **MySQL/MariaDB**: Any recent version
- **Commands**: mysql, mysqldump, gzip
- **Permissions**: Root or user with MySQL backup privileges
- **Disk Space**: Depends on database size (compressed ~30% of DB size)

## Security Considerations

1. **Configuration File**: Always `chmod 600` to protect credentials
2. **Backup Directory**: Restrict access (`chmod 750` or `700`)
3. **Replication User**: Grant only REPLICATION SLAVE privilege
4. **Network**: Use firewall to restrict replication traffic
5. **Backups**: Store off-site copies for disaster recovery
6. **Testing**: Regularly test restore procedures

## Compatibility

- ✅ **MariaDB**: All versions (5.5+)
- ✅ **MySQL**: 5.6, 5.7, 8.0+
- ✅ **Operating Systems**: Linux (Ubuntu, Debian, CentOS, RHEL)
- ✅ **Python**: 3.6, 3.7, 3.8, 3.9, 3.10, 3.11+
- ✅ **Schedulers**: Cron, Systemd timers

## Performance Notes

### Backup Times (Approximate)
- Small DB (< 1GB): < 1 minute
- Medium DB (1-10GB): 1-10 minutes
- Large DB (10-100GB): 10-60 minutes
- Very Large DB (> 100GB): 1+ hours

### Compression Ratios
- Text data: ~70-80% reduction
- Binary data: ~20-30% reduction
- Mixed: ~50% reduction average

### Disk Space Requirements
- Compressed backup: ~30% of database size
- Uncompressed: ~100% of database size
- Recommend: 3x database size free space

## Troubleshooting Common Issues

### "Connection failed"
- Check MySQL is running: `systemctl status mariadb`
- Verify credentials in config file
- Test: `mysql -u root -p`

### "Permission denied"
- Check config file: `chmod 600 mariadb_backup.conf`
- Check backup directory: `mkdir -p /path && chmod 750 /path`

### "Replication not starting"
- Verify master host is reachable
- Check replication user credentials
- Review master binary logging: `SHOW VARIABLES LIKE 'log_bin';`

### "Backup too slow"
- Use `--single-transaction` (already included)
- Increase network bandwidth
- Use faster storage
- Schedule during off-peak hours

## Getting Help

1. Check documentation:
   - README.md (comprehensive guide)
   - QUICK_REFERENCE.md (commands)
   - SYSTEMD_TIMERS.md (scheduling)

2. Run tests:
   - `./test_installation.py`

3. Check logs:
   - Backup log: `/var/log/mariadb_backup.log`
   - MySQL log: `/var/log/mysql/error.log`
   - Systemd: `journalctl -u mariadb-backup@daily`

4. Test manually:
   - Interactive menu: `./mariadb_manager.py`
   - Connection test: Option 9 in menu

## License

This project is provided as-is for free use and modification.

## Author

Created for managing MariaDB backups with full replication support.

## Version

Version: 1.0
Date: January 2026
