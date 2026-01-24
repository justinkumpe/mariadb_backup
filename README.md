# MariaDB Backup & Restore Manager

A comprehensive Python-based solution for managing MariaDB backups with support for master/slave replication configuration.

## Features

- ✅ **Complete Database Backups**: All databases, users, grants, and replication information
- ✅ **Multiple Backup Types**: Hourly, daily, and monthly with automatic overwrites
- ✅ **Automatic Slave Configuration**: Restore backups with automatic replication setup
- ✅ **Dual Operation Modes**: Interactive menu or command-line for cron jobs
- ✅ **Flexible Configuration**: Config file, command-line args, or interactive menu
- ✅ **Compression Support**: Optional gzip compression for space savings
- ✅ **Replication Aware**: Captures and restores binary log positions

## Installation

1. **Make the script executable**:
   ```bash
   chmod +x mariadb_manager.py
   ```

2. **Create configuration file**:
   ```bash
   cp mariadb_backup.conf.example mariadb_backup.conf
   nano mariadb_backup.conf
   ```

3. **Edit configuration** with your MySQL credentials and backup paths:
   ```ini
   [mysql]
   host = localhost
   user = root
   password = your_password
   port = 3306
   
   [backup_paths]
   hourly = /var/backups/mariadb/hourly
   daily = /var/backups/mariadb/daily
   monthly = /var/backups/mariadb/monthly
   
   [options]
   compression = yes
   ```

4. **Secure the configuration file**:
   ```bash
   chmod 600 mariadb_backup.conf
   ```

## Usage

### Interactive Menu Mode

Simply run without arguments for an interactive menu:

```bash
./mariadb_manager.py
```

Or with custom config:

```bash
./mariadb_manager.py --config /path/to/config.conf
```

### Command-Line Mode (for Cron Jobs)

#### Create Backups

```bash
# Hourly backup (same hour overwrites previous)
./mariadb_manager.py --backup hourly

# Daily backup (same day overwrites previous)
./mariadb_manager.py --backup daily

# Monthly backup (same month overwrites previous)
./mariadb_manager.py --backup monthly

# Manual backup with timestamp
./mariadb_manager.py --backup manual

# Manual backup to custom path
./mariadb_manager.py --backup manual --path /custom/backup/location
```

#### List Backups

```bash
# List all backups
./mariadb_manager.py --list

# List only daily backups
./mariadb_manager.py --list --type daily
```

#### Restore Backups

**Restore as Master/Standalone:**

```bash
./mariadb_manager.py --restore /var/backups/mariadb/daily/backup_20260122
```

**Restore as Slave (with automatic replication setup):**

```bash
./mariadb_manager.py --restore /var/backups/mariadb/daily/backup_20260122 \
  --slave \
  --master-host 192.168.1.100 \
  --master-user replication_user \
  --master-password replication_password
```

## Cron Job Setup

### Option 1: Using Crontab

Edit crontab:
```bash
crontab -e
```

Add these lines:

```bash
# MariaDB Backups
# Hourly backup at minute 0
0 * * * * /usr/local/bin/mariadb_manager.py --backup hourly --config /root/mariadb_backup.conf >> /var/log/mariadb_backup.log 2>&1

# Daily backup at 2 AM
0 2 * * * /usr/local/bin/mariadb_manager.py --backup daily --config /root/mariadb_backup.conf >> /var/log/mariadb_backup.log 2>&1

# Monthly backup on 1st at 3 AM
0 3 1 * * /usr/local/bin/mariadb_manager.py --backup monthly --config /root/mariadb_backup.conf >> /var/log/mariadb_backup.log 2>&1
```

### Option 2: Using Systemd Timers

Create service file `/etc/systemd/system/mariadb-backup@.service`:

```ini
[Unit]
Description=MariaDB Backup (%i)

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mariadb_manager.py --backup %i --config /root/mariadb_backup.conf
User=root
```

Create timer files:

**Hourly** (`/etc/systemd/system/mariadb-backup-hourly.timer`):
```ini
[Unit]
Description=MariaDB Hourly Backup Timer

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

**Daily** (`/etc/systemd/system/mariadb-backup-daily.timer`):
```ini
[Unit]
Description=MariaDB Daily Backup Timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

**Monthly** (`/etc/systemd/system/mariadb-backup-monthly.timer`):
```ini
[Unit]
Description=MariaDB Monthly Backup Timer

[Timer]
OnCalendar=monthly
Persistent=true

[Install]
WantedBy=timers.target
```

Enable timers:
```bash
systemctl daemon-reload
systemctl enable --now mariadb-backup-hourly.timer
systemctl enable --now mariadb-backup-daily.timer
systemctl enable --now mariadb-backup-monthly.timer
```

Check status:
```bash
systemctl list-timers | grep mariadb
```

## Backup Structure

Each backup contains:

```
backup_YYYYMMDD_HH/
├── all_databases.sql.gz          # All databases with structure and data
├── users_and_grants.sql.gz       # User accounts and grants
├── replication_info.json         # Binary log position and server info
└── MANIFEST.txt                  # Backup metadata and file list
```

### Replication Info Format

```json
{
  "backup_time": "2026-01-22T10:30:00",
  "backup_type": "daily",
  "master_status": {
    "binlog_file": "mysql-bin.000123",
    "binlog_position": "45678",
    "binlog_do_db": "",
    "binlog_ignore_db": ""
  },
  "server_id": "1",
  "server_uuid": "abc123-def456-..."
}
```

## Backup Overwrite Behavior

- **Hourly**: Backups with same YYYYMMDD_HH overwrite (24 backups max per location)
- **Daily**: Backups with same YYYYMMDD overwrite (31 backups max per location)
- **Monthly**: Backups with same YYYYMM overwrite (12 backups max per location)
- **Manual**: Uses full timestamp, never overwrites

## Setting Up Replication

### On Master Server

1. Enable binary logging in `/etc/mysql/mariadb.conf.d/50-server.cnf`:
   ```ini
   [mysqld]
   server-id = 1
   log-bin = /var/log/mysql/mysql-bin.log
   binlog-format = ROW
   ```

2. Create replication user:
   ```sql
   CREATE USER 'replication_user'@'%' IDENTIFIED BY 'strong_password';
   GRANT REPLICATION SLAVE ON *.* TO 'replication_user'@'%';
   FLUSH PRIVILEGES;
   ```

3. Create backup:
   ```bash
   ./mariadb_manager.py --backup daily
   ```

### On Slave Server

1. Configure unique server ID in `/etc/mysql/mariadb.conf.d/50-server.cnf`:
   ```ini
   [mysqld]
   server-id = 2
   log-bin = /var/log/mysql/mysql-bin.log
   relay-log = /var/log/mysql/mysql-relay-bin
   read_only = 1
   ```

2. Restart MySQL:
   ```bash
   systemctl restart mariadb
   ```

3. Restore backup as slave (automatically configures replication):
   ```bash
   ./mariadb_manager.py --restore /path/to/backup \
     --slave \
     --master-host 192.168.1.100 \
     --master-user replication_user \
     --master-password strong_password
   ```

4. Check replication status:
   ```bash
   mysql -e "SHOW SLAVE STATUS\G"
   ```

   Look for:
   - `Slave_IO_Running: Yes`
   - `Slave_SQL_Running: Yes`
   - `Seconds_Behind_Master: 0`

## Manual Restoration (Without Script)

If you need to restore manually:

```bash
# 1. Extract database backup
cd /path/to/backup
gunzip -c all_databases.sql.gz | mysql -u root -p

# 2. Extract and restore users (optional)
gunzip -c users_and_grants.sql.gz | mysql -u root -p

# 3. For slave setup, read replication info
cat replication_info.json

# 4. Configure slave manually
mysql -u root -p <<EOF
STOP SLAVE;
CHANGE MASTER TO
  MASTER_HOST='192.168.1.100',
  MASTER_USER='replication_user',
  MASTER_PASSWORD='strong_password',
  MASTER_PORT=3306,
  MASTER_LOG_FILE='mysql-bin.000123',
  MASTER_LOG_POS=45678;
START SLAVE;
SHOW SLAVE STATUS\G
EOF
```

## Troubleshooting

### Connection Issues

Test connection:
```bash
./mariadb_manager.py --config mariadb_backup.conf
# Then select option 9 (Test MySQL Connection)
```

Or manually:
```bash
mysql --host=localhost --user=root --password=yourpass -e "SELECT 1;"
```

### Backup Failures

Check MySQL error log:
```bash
tail -f /var/log/mysql/error.log
```

Test mysqldump manually:
```bash
mysqldump --host=localhost --user=root --password=yourpass \
  --single-transaction --routines --triggers --events \
  --databases test > /tmp/test_backup.sql
```

### Replication Issues

On slave, check status:
```sql
SHOW SLAVE STATUS\G
```

Common issues:
- **Slave_IO_Running: No** - Check master connectivity, credentials
- **Slave_SQL_Running: No** - Check `Last_SQL_Error` for details
- **Seconds_Behind_Master: High** - Slave is catching up

Reset and reconfigure slave:
```sql
STOP SLAVE;
RESET SLAVE;
-- Run CHANGE MASTER TO again with correct parameters
START SLAVE;
```

### Permissions

Ensure config file is secure:
```bash
chmod 600 mariadb_backup.conf
```

Ensure backup directories are writable:
```bash
mkdir -p /var/backups/mariadb/{hourly,daily,monthly}
chmod 750 /var/backups/mariadb/{hourly,daily,monthly}
```

## Security Best Practices

1. **Secure Configuration File**: Always `chmod 600` config files
2. **Strong Passwords**: Use strong passwords for MySQL root and replication users
3. **Network Security**: Restrict replication to specific IPs using firewall
4. **Backup Encryption**: Enable encryption in options (future feature)
5. **Regular Testing**: Regularly test restore procedures
6. **Off-site Backups**: Copy backups to remote storage

## Monitoring

Create a monitoring script `/usr/local/bin/check_mariadb_backups.sh`:

```bash
#!/bin/bash

BACKUP_DIRS="/var/backups/mariadb/hourly /var/backups/mariadb/daily /var/backups/mariadb/monthly"
MAX_AGE_HOURS=26  # Alert if daily backup is older than 26 hours

for DIR in $BACKUP_DIRS; do
    if [ -d "$DIR" ]; then
        LATEST=$(find "$DIR" -type d -name "backup_*" -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2)
        if [ -n "$LATEST" ]; then
            AGE_HOURS=$(( ($(date +%s) - $(stat -c %Y "$LATEST")) / 3600 ))
            echo "$(basename $DIR): Latest backup is $AGE_HOURS hours old"
            
            if [ $AGE_HOURS -gt $MAX_AGE_HOURS ]; then
                echo "WARNING: Backup is too old!"
            fi
        else
            echo "WARNING: No backups found in $DIR"
        fi
    fi
done
```

Add to cron for daily checks:
```bash
0 8 * * * /usr/local/bin/check_mariadb_backups.sh | mail -s "MariaDB Backup Status" admin@example.com
```

## License

This script is provided as-is for free use and modification.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review MySQL/MariaDB logs
3. Test individual components (connection, mysqldump, etc.)
