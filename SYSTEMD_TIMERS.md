# Systemd Timer Setup for MariaDB Backups

This is an alternative to cron for scheduling backups using systemd timers.

## Installation

### 1. Create the service file

Create `/etc/systemd/system/mariadb-backup@.service`:

```ini
[Unit]
Description=MariaDB Backup (%i)
After=mariadb.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mariadb_manager.py --backup %i --config /etc/mariadb_backup.conf
StandardOutput=journal
StandardError=journal
User=root
Nice=10
IOSchedulingClass=idle
```

### 2. Create timer files

**Hourly Timer** - `/etc/systemd/system/mariadb-backup-hourly.timer`:

```ini
[Unit]
Description=MariaDB Hourly Backup Timer
Requires=mariadb.service

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
```

**Daily Timer** - `/etc/systemd/system/mariadb-backup-daily.timer`:

```ini
[Unit]
Description=MariaDB Daily Backup Timer
Requires=mariadb.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true
RandomizedDelaySec=15min

[Install]
WantedBy=timers.target
```

**Monthly Timer** - `/etc/systemd/system/mariadb-backup-monthly.timer`:

```ini
[Unit]
Description=MariaDB Monthly Backup Timer
Requires=mariadb.service

[Timer]
OnCalendar=monthly
OnCalendar=*-*-01 03:00:00
Persistent=true
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
```

### 3. Enable and start timers

```bash
# Reload systemd
systemctl daemon-reload

# Enable timers (start on boot)
systemctl enable mariadb-backup-hourly.timer
systemctl enable mariadb-backup-daily.timer
systemctl enable mariadb-backup-monthly.timer

# Start timers now
systemctl start mariadb-backup-hourly.timer
systemctl start mariadb-backup-daily.timer
systemctl start mariadb-backup-monthly.timer
```

## Management Commands

### Check timer status
```bash
# List all timers
systemctl list-timers

# Filter for MariaDB backups
systemctl list-timers | grep mariadb

# Check specific timer status
systemctl status mariadb-backup-daily.timer
```

### View logs
```bash
# View all backup logs
journalctl -u mariadb-backup@*

# View specific backup type logs
journalctl -u mariadb-backup@daily

# Follow logs in real-time
journalctl -u mariadb-backup@daily -f

# View last 50 lines
journalctl -u mariadb-backup@daily -n 50

# View logs from today
journalctl -u mariadb-backup@* --since today

# View logs with timestamps
journalctl -u mariadb-backup@daily -o short-iso
```

### Manually trigger backup
```bash
# Run daily backup now
systemctl start mariadb-backup@daily.service

# Check status
systemctl status mariadb-backup@daily.service
```

### Stop/disable timers
```bash
# Stop timer (won't run until started again)
systemctl stop mariadb-backup-hourly.timer

# Disable timer (won't start on boot)
systemctl disable mariadb-backup-hourly.timer

# Both stop and disable
systemctl disable --now mariadb-backup-hourly.timer
```

### Restart/reload timers
```bash
# After changing timer files
systemctl daemon-reload
systemctl restart mariadb-backup-daily.timer
```

## Timer Options Explained

### OnCalendar
- `hourly` - Every hour at :00
- `daily` - Every day at 00:00
- `weekly` - Every Monday at 00:00
- `monthly` - 1st of each month at 00:00
- `*-*-01 03:00:00` - 1st of month at 3 AM
- `Mon 08:00` - Every Monday at 8 AM
- `*:0/15` - Every 15 minutes

### Persistent
If `true`, missed runs (system was off) will trigger when system starts.

### RandomizedDelaySec
Adds random delay to prevent all backups running at exact same time. Useful for system load distribution.

### Nice and IOSchedulingClass
- `Nice=10` - Lower CPU priority (range: -20 to 19, higher = lower priority)
- `IOSchedulingClass=idle` - Run only when system I/O is idle

## Advanced Timer Examples

### Every 6 hours
```ini
[Timer]
OnCalendar=0/6:00:00
```

### Twice daily (6 AM and 6 PM)
```ini
[Timer]
OnCalendar=06:00
OnCalendar=18:00
```

### Weekday backups only
```ini
[Timer]
OnCalendar=Mon,Tue,Wed,Thu,Fri 02:00
```

### Every 2nd and 4th Sunday
```ini
[Timer]
OnCalendar=Sun *-*-8,9,10,11,12,13,14 03:00
OnCalendar=Sun *-*-22,23,24,25,26,27,28 03:00
```

## Complete Installation Script

Save as `setup_systemd_timers.sh`:

```bash
#!/bin/bash

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root"
   exit 1
fi

# Create service file
cat > /etc/systemd/system/mariadb-backup@.service <<'EOF'
[Unit]
Description=MariaDB Backup (%i)
After=mariadb.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mariadb_manager.py --backup %i --config /etc/mariadb_backup.conf
StandardOutput=journal
StandardError=journal
User=root
Nice=10
IOSchedulingClass=idle
EOF

# Create hourly timer
cat > /etc/systemd/system/mariadb-backup-hourly.timer <<'EOF'
[Unit]
Description=MariaDB Hourly Backup Timer
Requires=mariadb.service

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=5min

[Install]
WantedBy=timers.target
EOF

# Create daily timer
cat > /etc/systemd/system/mariadb-backup-daily.timer <<'EOF'
[Unit]
Description=MariaDB Daily Backup Timer
Requires=mariadb.service

[Timer]
OnCalendar=02:00
Persistent=true
RandomizedDelaySec=15min

[Install]
WantedBy=timers.target
EOF

# Create monthly timer
cat > /etc/systemd/system/mariadb-backup-monthly.timer <<'EOF'
[Unit]
Description=MariaDB Monthly Backup Timer
Requires=mariadb.service

[Timer]
OnCalendar=*-*-01 03:00:00
Persistent=true
RandomizedDelaySec=30min

[Install]
WantedBy=timers.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable and start timers
systemctl enable --now mariadb-backup-hourly.timer
systemctl enable --now mariadb-backup-daily.timer
systemctl enable --now mariadb-backup-monthly.timer

echo "Systemd timers installed and started!"
echo ""
echo "Check status with:"
echo "  systemctl list-timers | grep mariadb"
echo ""
echo "View logs with:"
echo "  journalctl -u mariadb-backup@daily -f"
```

Make it executable and run:
```bash
chmod +x setup_systemd_timers.sh
./setup_systemd_timers.sh
```

## Monitoring with systemd

### Email notifications on failure

Create `/etc/systemd/system/mariadb-backup-notify@.service`:

```ini
[Unit]
Description=MariaDB Backup Failure Notification
After=mariadb-backup@%i.service
PartOf=mariadb-backup@%i.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup-notify.sh %i
User=root
```

Then modify the main service to include:
```ini
[Unit]
OnFailure=mariadb-backup-notify@%i.service
```

### Create notification script

`/usr/local/bin/backup-notify.sh`:

```bash
#!/bin/bash
BACKUP_TYPE=$1
echo "MariaDB $BACKUP_TYPE backup failed at $(date)" | \
  mail -s "ALERT: MariaDB Backup Failed" admin@example.com
```

## Troubleshooting

### Timer not running
```bash
# Check if timer is active
systemctl is-active mariadb-backup-daily.timer

# Check timer status
systemctl status mariadb-backup-daily.timer

# Check for errors
journalctl -xeu mariadb-backup-daily.timer
```

### Service failing
```bash
# Check service status
systemctl status mariadb-backup@daily.service

# View detailed logs
journalctl -xeu mariadb-backup@daily.service

# Test manually
systemctl start mariadb-backup@daily.service
```

### View next scheduled run
```bash
systemctl list-timers mariadb-backup-*
```

## Comparison: Systemd vs Cron

### Advantages of Systemd Timers
- ✅ Better logging (journalctl)
- ✅ Dependencies (wait for MariaDB)
- ✅ Automatic retry on failure
- ✅ Persistent (run missed jobs)
- ✅ Resource control (Nice, IO priority)
- ✅ Calendar events (more flexible)

### Advantages of Cron
- ✅ Simpler syntax
- ✅ Universal (works everywhere)
- ✅ User-level jobs without root
- ✅ Environment variables easier

### Recommendation
Use **systemd timers** for production systems with systemd. Use **cron** for simpler setups or non-systemd systems.
