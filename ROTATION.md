# Backup Rotation Feature

## Overview
The backup rotation feature automatically manages backup retention by deleting old backups based on configurable limits for each backup type (hourly, daily, monthly).

## Configuration

Add the `[rotation]` section to your `mariadb_backup.conf`:

```ini
[rotation]
hourly_keep = 24    # Keep last 24 hourly backups
daily_keep = 31     # Keep last 31 daily backups
monthly_keep = 12   # Keep last 12 monthly backups
```

**Note:** Set any value to `0` to disable rotation for that type (unlimited backups).

## How It Works

1. **Automatic Cleanup**: After each successful backup, rotation cleanup runs automatically
2. **Sort by Time**: Backups are sorted by modification time (newest first)
3. **Keep N Newest**: The configured number of backups are kept
4. **Delete Oldest**: Any backups beyond the limit are automatically deleted

## Examples

### Standard Configuration
```ini
[rotation]
hourly_keep = 24    # 1 day of hourly backups
daily_keep = 31     # 1 month of daily backups
monthly_keep = 12   # 1 year of monthly backups
```

### Conservative (More Backups)
```ini
[rotation]
hourly_keep = 48    # 2 days of hourly backups
daily_keep = 90     # 3 months of daily backups
monthly_keep = 24   # 2 years of monthly backups
```

### Aggressive (Fewer Backups)
```ini
[rotation]
hourly_keep = 6     # 6 hours of backups
daily_keep = 7      # 1 week of daily backups
monthly_keep = 3    # 3 months of monthly backups
```

### Selective Retention
```ini
[rotation]
hourly_keep = 0     # Keep all hourly backups (no rotation)
daily_keep = 14     # Keep 2 weeks of daily backups
monthly_keep = 0    # Keep all monthly backups (no rotation)
```

## Configuration Methods

### Method 1: Edit Config File Directly
```bash
nano mariadb_backup.conf
```

Add or modify the `[rotation]` section, then save.

### Method 2: Interactive Menu
```bash
./mariadb_manager.py
# Select option 8: Configure Settings
# Select option 4: Backup Rotation Settings
# Enter desired values
# Select option 7: Save and Exit
```

### Method 3: Create New Config from Example
```bash
cp mariadb_backup.conf.example mariadb_backup.conf
nano mariadb_backup.conf
# Edit the [rotation] section
```

## Monitoring Rotation

### Check Backup Counts
```bash
# Count hourly backups
ls -1 /var/backups/mariadb/hourly/ | wc -l

# Count daily backups
ls -1 /var/backups/mariadb/daily/ | wc -l

# Count monthly backups
ls -1 /var/backups/mariadb/monthly/ | wc -l
```

### View Rotation in Action
When a backup runs with rotation enabled, you'll see output like:
```
[6/6] Cleaning up old backups...
Keeping last 24 hourly backups...
  Deleted old backup: backup_20240120_10
  Deleted old backup: backup_20240120_09
Deleted 2 old backup(s)
```

### Check Disk Usage
```bash
# Check total backup directory size
du -sh /var/backups/mariadb/*

# Check individual backup sizes
du -h /var/backups/mariadb/hourly/ | sort -h
```

## Troubleshooting

### Rotation Not Working
1. **Check Config Values**: Ensure `_keep` values are greater than 0
   ```bash
   grep -A3 '\[rotation\]' mariadb_backup.conf
   ```

2. **Verify Config Location**: Make sure you're editing the correct config file
   ```bash
   ./mariadb_manager.py
   # Check the "Config:" line at the top of the menu
   ```

3. **Check Permissions**: Ensure the script can delete files
   ```bash
   ls -la /var/backups/mariadb/hourly/
   ```

### Too Many Backups Being Deleted
- Increase the `_keep` value in your config
- Check that backups aren't being created more frequently than expected
- Verify cron schedule matches backup type (e.g., hourly backups shouldn't run every minute)

### Backups Not Being Deleted
- Verify rotation config is set (not 0)
- Check that you have more backups than the `_keep` limit
- Review backup logs for rotation errors
- Ensure backups follow the naming pattern `backup_*`

## Disk Space Planning

### Calculate Space Requirements

**Example calculation for daily backups:**
- Average backup size: 500 MB
- Daily backups to keep: 31
- Estimated space: 500 MB × 31 = 15.5 GB

**Full backup set example:**
```
Hourly: 500 MB × 24 = 12 GB
Daily:  500 MB × 31 = 15.5 GB
Monthly: 500 MB × 12 = 6 GB
Total: ~34 GB
```

### Monitoring Commands
```bash
# Watch disk usage in real-time
watch -n 60 'df -h /var/backups/mariadb'

# Get detailed backup statistics
du -sh /var/backups/mariadb/*/* | sort -h | tail -20
```

## Best Practices

1. **Start Conservative**: Begin with higher retention values, then adjust based on disk space
2. **Monitor Regularly**: Check disk usage weekly, especially initially
3. **Test Restores**: Verify old backups before rotation deletes them
4. **Match Schedule**: Align rotation with backup schedule (24 hourly for daily cycle)
5. **Consider Growth**: Factor in database growth when planning retention
6. **Off-site Backups**: Keep copies elsewhere before aggressive rotation
7. **Document Changes**: Note rotation config changes in change log

## Safety Features

- **Non-zero Check**: Rotation only runs if `_keep > 0`
- **Sorted by Time**: Always deletes oldest first
- **Individual Handling**: Each backup type rotates independently
- **Error Handling**: Failed deletions are logged but don't stop the backup
- **Manifest Protected**: Only directories matching `backup_*` pattern are affected

## Integration with Cron

Rotation happens automatically with each backup:

```bash
# Crontab example - rotation runs after each backup
0 * * * * /usr/local/bin/mariadb_manager.py --backup hourly --config /root/mariadb_backup.conf
```

No separate rotation cron job is needed.
