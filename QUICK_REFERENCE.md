# Quick Reference Guide

## Quick Start

```bash
# 1. Install
chmod +x install.sh mariadb_manager.py
./install.sh

# 2. Interactive menu
./mariadb_manager.py

# 3. Or command line
./mariadb_manager.py --backup daily
```

## Common Commands

### Backups
```bash
# Cron-friendly backups (overwrites same period)
./mariadb_manager.py --backup hourly    # Overwrites same hour
./mariadb_manager.py --backup daily     # Overwrites same day  
./mariadb_manager.py --backup monthly   # Overwrites same month

# Manual backup (never overwrites)
./mariadb_manager.py --backup manual
./mariadb_manager.py --backup manual --path /custom/path
```

### Listing Backups
```bash
./mariadb_manager.py --list              # All backups
./mariadb_manager.py --list --type daily # Daily only
```

### Restore

**As Master/Standalone:**
```bash
./mariadb_manager.py --restore /var/backups/mariadb/daily/backup_20260122
```

**As Slave (auto-configure replication):**
```bash
./mariadb_manager.py --restore /var/backups/mariadb/daily/backup_20260122 \
  --slave \
  --master-host 192.168.1.100 \
  --master-user repl_user \
  --master-password secret123
```

## Crontab Examples

```bash
# Edit crontab
crontab -e

# Add these lines:

# Hourly backup (keeps last 24)
0 * * * * /usr/local/bin/mariadb_manager.py --backup hourly >> /var/log/mariadb_backup.log 2>&1

# Daily backup at 2 AM (keeps last 31)
0 2 * * * /usr/local/bin/mariadb_manager.py --backup daily >> /var/log/mariadb_backup.log 2>&1

# Monthly backup on 1st at 3 AM (keeps last 12)
0 3 1 * * /usr/local/bin/mariadb_manager.py --backup monthly >> /var/log/mariadb_backup.log 2>&1
```

## Configuration File

**Location:** `/etc/mariadb_backup.conf` or `./mariadb_backup.conf`

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

**Secure it:**
```bash
chmod 600 mariadb_backup.conf
```

## Backup Structure

```
backup_YYYYMMDD_HH/
├── all_databases.sql.gz          # All databases
├── users_and_grants.sql.gz       # Users & grants
├── replication_info.json         # Binlog position
└── MANIFEST.txt                  # Metadata
```

## Replication Setup

### Master Server

1. **Enable binary logging** in `/etc/mysql/mariadb.conf.d/50-server.cnf`:
   ```ini
   [mysqld]
   server-id = 1
   log-bin = mysql-bin
   ```

2. **Create replication user:**
   ```sql
   CREATE USER 'repl_user'@'%' IDENTIFIED BY 'secret123';
   GRANT REPLICATION SLAVE ON *.* TO 'repl_user'@'%';
   FLUSH PRIVILEGES;
   ```

3. **Create backup:**
   ```bash
   ./mariadb_manager.py --backup daily
   ```

### Slave Server

1. **Configure unique server ID** in `/etc/mysql/mariadb.conf.d/50-server.cnf`:
   ```ini
   [mysqld]
   server-id = 2
   read_only = 1
   ```

2. **Restart MySQL:**
   ```bash
   systemctl restart mariadb
   ```

3. **Restore as slave:**
   ```bash
   ./mariadb_manager.py --restore /path/to/backup \
     --slave \
     --master-host 192.168.1.100 \
     --master-user repl_user \
     --master-password secret123
   ```

4. **Verify:**
   ```sql
   SHOW SLAVE STATUS\G
   ```
   Check: `Slave_IO_Running: Yes` and `Slave_SQL_Running: Yes`

## Troubleshooting

### Test Connection
```bash
./mariadb_manager.py
# Select: 9. Test MySQL Connection
```

### Test mysqldump manually
```bash
mysqldump --host=localhost --user=root --password=yourpass \
  --single-transaction test > /tmp/test.sql
```

### Check logs
```bash
tail -f /var/log/mariadb_backup.log
tail -f /var/log/mysql/error.log
```

### Check replication status
```sql
SHOW SLAVE STATUS\G
```

### Reset slave
```sql
STOP SLAVE;
RESET SLAVE;
-- Configure again with CHANGE MASTER TO
START SLAVE;
```

### Fix permissions
```bash
chmod 600 mariadb_backup.conf
chmod 750 /var/backups/mariadb/*
```

## One-Liners

### Create immediate backup
```bash
./mariadb_manager.py --backup manual
```

### List backups sorted by size
```bash
du -sh /var/backups/mariadb/*/*/ | sort -h
```

### Find latest backup
```bash
find /var/backups/mariadb -type d -name "backup_*" -printf '%T@ %p\n' | sort -nr | head -1
```

### Check backup age
```bash
stat -c '%y' /var/backups/mariadb/daily/backup_*
```

### Verify backup integrity
```bash
# Check if compressed files are valid
gunzip -t /var/backups/mariadb/daily/backup_*/all_databases.sql.gz
```

### Test restore (dry run - list only)
```bash
gunzip -c /var/backups/mariadb/daily/backup_*/all_databases.sql.gz | head -100
```

### Monitor backup sizes
```bash
watch -n 60 'du -sh /var/backups/mariadb/*'
```

### Count databases in backup
```bash
gunzip -c backup_*/all_databases.sql.gz | grep "^CREATE DATABASE" | wc -l
```

## Performance Tips

1. **Use --single-transaction** (already included) for InnoDB tables
2. **Run backups during low-traffic periods** (2-4 AM recommended)
3. **Enable compression** (saves ~70% space)
4. **Use fast storage** for backup destination
5. **Monitor disk space** regularly

## Security Checklist

- [ ] Config file permissions: `chmod 600`
- [ ] Strong MySQL root password
- [ ] Strong replication password
- [ ] Firewall rules for replication port
- [ ] Backup directory permissions
- [ ] Regular restore testing
- [ ] Off-site backup copies
- [ ] Audit logs enabled

## Monitoring Script

Save as `/usr/local/bin/check_backups.sh`:

```bash
#!/bin/bash
DIRS="/var/backups/mariadb/hourly /var/backups/mariadb/daily"
for DIR in $DIRS; do
    LATEST=$(find "$DIR" -type d -name "backup_*" -printf '%T@ %p\n' | sort -nr | head -1)
    if [ -n "$LATEST" ]; then
        AGE=$(( ($(date +%s) - $(echo $LATEST | cut -d' ' -f1 | cut -d. -f1)) / 3600 ))
        echo "$(basename $DIR): $AGE hours old"
    fi
done
```

Add to cron:
```bash
0 8 * * * /usr/local/bin/check_backups.sh | mail -s "Backup Status" admin@example.com
```
