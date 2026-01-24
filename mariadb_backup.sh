root@vps10:~# cat mariadb_backup_v2.sh 
#!/bin/bash

# MariaDB Complete Encrypted Backup Script
# Creates full backup including databases, users, grants, and system settings

set -euo pipefail

# Configuration
BACKUP_DIR="/home/mariadb_backups"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="mariadb_full_${TIMESTAMP}"
MYSQL_CREDS_FILE="/root/.mariadb_credentials"
ENCRYPTION_PASSWORD_FILE="/root/.mariadb_backup_key"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   error "This script must be run as root"
   exit 1
fi

# Check if MySQL credentials file exists
if [[ ! -f "$MYSQL_CREDS_FILE" ]]; then
    error "MySQL credentials file not found at $MYSQL_CREDS_FILE"
    echo ""
    echo "Create it with:"
    echo "cat > $MYSQL_CREDS_FILE << 'EOF'"
    echo "[client]"
    echo "user=root"
    echo "password=your_mysql_password"
    echo "EOF"
    echo "chmod 600 $MYSQL_CREDS_FILE"
    exit 1
fi

# Check credentials file permissions
CREDS_PERMS=$(stat -c %a "$MYSQL_CREDS_FILE")
if [[ "$CREDS_PERMS" != "600" ]]; then
    error "Insecure permissions on $MYSQL_CREDS_FILE (currently $CREDS_PERMS)"
    echo "Fix with: chmod 600 $MYSQL_CREDS_FILE"
    exit 1
fi

# Check if encryption password file exists
if [[ ! -f "$ENCRYPTION_PASSWORD_FILE" ]]; then
    error "Encryption password file not found at $ENCRYPTION_PASSWORD_FILE"
    echo "Create it with: echo 'your-strong-password' > $ENCRYPTION_PASSWORD_FILE && chmod 600 $ENCRYPTION_PASSWORD_FILE"
    exit 1
fi

# Check encryption file permissions
ENC_PERMS=$(stat -c %a "$ENCRYPTION_PASSWORD_FILE")
if [[ "$ENC_PERMS" != "600" ]]; then
    error "Insecure permissions on $ENCRYPTION_PASSWORD_FILE (currently $ENC_PERMS)"
    echo "Fix with: chmod 600 $ENCRYPTION_PASSWORD_FILE"
    exit 1
fi

# Check required commands
for cmd in mysqldump mysql openssl gzip tar; do
    if ! command -v $cmd &> /dev/null; then
        error "$cmd is required but not installed"
        exit 1
    fi
done

# Create backup directory
mkdir -p "$BACKUP_DIR"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
mkdir -p "$BACKUP_PATH"

log "Starting MariaDB backup to $BACKUP_PATH"

# Test MySQL connection
if ! mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -e "SELECT 1;" &> /dev/null; then
    error "Failed to connect to MySQL. Check credentials in $MYSQL_CREDS_FILE"
    exit 1
fi

log "MySQL connection successful"

# 1. Backup all databases
log "Backing up all databases..."
mysqldump --defaults-extra-file="$MYSQL_CREDS_FILE" \
    --all-databases \
    --single-transaction \
    --routines \
    --triggers \
    --events \
    --flush-privileges \
    --hex-blob \
    --master-data=2 \
    --add-drop-database \
    --quick \
    --compress \
    2> "$BACKUP_PATH/mysqldump_errors.log" | \
    gzip > "$BACKUP_PATH/all_databases.sql.gz"

if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    error "Database backup failed. Check $BACKUP_PATH/mysqldump_errors.log"
    cat "$BACKUP_PATH/mysqldump_errors.log"
    exit 1
fi
log "Database backup completed"

# 2. Backup users and grants separately (for easier restoration)
log "Backing up users and grants..."
mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -N -B -e \
    "SELECT CONCAT('SHOW CREATE USER ''', user, '''@''', host, ''';') 
     FROM mysql.global_priv WHERE user NOT IN ('mysql.sys', 'mariadb.sys')" | \
    mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -N -B 2>/dev/null | \
    sed 's/$/;/' > "$BACKUP_PATH/users.sql"

mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -N -B -e \
    "SELECT CONCAT('SHOW GRANTS FOR ''', user, '''@''', host, ''';') 
     FROM mysql.global_priv WHERE user NOT IN ('mysql.sys', 'mariadb.sys')" | \
    mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -N -B 2>/dev/null | \
    sed 's/$/;/' >> "$BACKUP_PATH/users.sql"

gzip "$BACKUP_PATH/users.sql"
log "Users and grants backup completed"

# 3. Backup MySQL configuration
log "Backing up MySQL configuration..."
if [[ -f /etc/mysql/mariadb.conf.d/50-server.cnf ]]; then
    cp /etc/mysql/mariadb.conf.d/50-server.cnf "$BACKUP_PATH/"
fi
if [[ -f /etc/my.cnf ]]; then
    cp /etc/my.cnf "$BACKUP_PATH/"
fi
if [[ -d /etc/mysql ]]; then
    tar -czf "$BACKUP_PATH/mysql_config.tar.gz" -C /etc mysql/ 2>/dev/null || true
fi
log "Configuration backup completed"

# 4. Create backup manifest
log "Creating backup manifest..."
cat > "$BACKUP_PATH/backup_manifest.txt" <<EOF
Backup Date: $(date)
MariaDB Version: $(mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -V 2>/dev/null)
Server Hostname: $(hostname)
Backup Type: Full (All databases + users + grants + config)
Encryption: AES-256-CBC

Files included:
- all_databases.sql.gz (All databases with structure and data)
- users.sql.gz (User accounts and grants)
- mysql_config.tar.gz (MySQL/MariaDB configuration files)
- backup_manifest.txt (This file)
- checksums.sha256 (File integrity checksums)

Restoration Instructions:
1. Decrypt: openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/root/.mariadb_backup_key -in backup.tar.gz.enc -out backup.tar.gz
2. Extract: tar -xzf backup.tar.gz
3. Verify: cd extracted_folder && sha256sum -c checksums.sha256
4. Restore databases: gunzip < all_databases.sql.gz | mysql -u root -p
5. Restore users (optional): gunzip < users.sql.gz | mysql -u root -p
6. Review and apply configuration changes as needed

Database List:
EOF

mysql --defaults-extra-file="$MYSQL_CREDS_FILE" -N -B -e \
    "SELECT CONCAT(schema_name, ' (', 
     ROUND(SUM(data_length + index_length) / 1024 / 1024, 2), ' MB)') 
     FROM information_schema.SCHEMATA 
     LEFT JOIN information_schema.TABLES USING (schema_name) 
     WHERE schema_name NOT IN ('information_schema', 'performance_schema') 
     GROUP BY schema_name 
     ORDER BY schema_name" >> "$BACKUP_PATH/backup_manifest.txt"

log "Manifest created"

# 5. Create checksums
log "Creating checksums..."
cd "$BACKUP_PATH"
sha256sum *.gz *.txt *.log 2>/dev/null > checksums.sha256 || true
cd - > /dev/null
log "Checksums created"

# 6. Compress and encrypt the backup
log "Compressing and encrypting backup..."
tar -czf - -C "$BACKUP_DIR" "$BACKUP_NAME" | \
    openssl enc -aes-256-cbc -salt -pbkdf2 \
    -pass file:"$ENCRYPTION_PASSWORD_FILE" \
    -out "$BACKUP_DIR/${BACKUP_NAME}.tar.gz.enc"

if [[ ${PIPESTATUS[0]} -ne 0 ]] || [[ ${PIPESTATUS[1]} -ne 0 ]]; then
    error "Encryption failed"
    exit 1
fi

# Remove unencrypted directory
rm -rf "$BACKUP_PATH"
log "Backup encrypted successfully"

# 7. Verify encrypted backup
BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.tar.gz.enc" | cut -f1)
log "Encrypted backup size: $BACKUP_SIZE"

# 8. Cleanup old backups
log "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "mariadb_full_*.tar.gz.enc" -type f -mtime +$RETENTION_DAYS -delete
REMAINING=$(find "$BACKUP_DIR" -name "mariadb_full_*.tar.gz.enc" -type f | wc -l)
log "Remaining backups: $REMAINING"

# 9. Final summary
log "=========================================="
log "Backup completed successfully!"
log "Location: $BACKUP_DIR/${BACKUP_NAME}.tar.gz.enc"
log "Size: $BACKUP_SIZE"
log "=========================================="

# Optional: Test decryption (just verify, don't extract)
log "Verifying encryption integrity..."
if openssl enc -d -aes-256-cbc -pbkdf2 \
    -pass file:"$ENCRYPTION_PASSWORD_FILE" \
    -in "$BACKUP_DIR/${BACKUP_NAME}.tar.gz.enc" | tar -tz > /dev/null 2>&1; then
root@vps10:~# 
