#!/bin/bash

# Provision a fresh MariaDB server for mariadb_manager.py restore operations.
# - Installs MariaDB server/client packages (unless --skip-install)
# - Starts and enables MariaDB service
# - Creates/updates a restore admin user
# - Writes mariadb_backup.conf compatible config file

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DB_ADMIN_USER="restore_admin"
DB_ADMIN_PASS=""
DB_ADMIN_HOST="localhost"
CONFIG_PATH="/etc/mariadb_backup.conf"
BACKUP_ROOT="/var/backups/mariadb"
MYSQL_HOST="localhost"
MYSQL_PORT="3306"
SKIP_INSTALL=0
SKIP_CONFIG_WRITE=0
NON_INTERACTIVE=0
FORCE=0

print_usage() {
  cat <<EOF
Usage: $SCRIPT_NAME [options]

Options:
  --db-admin-user USER       MariaDB user for restore tool (default: restore_admin)
  --db-admin-pass PASS       MariaDB password for restore user (required unless interactive)
  --db-admin-host HOST       Host part for MariaDB user (default: localhost)
  --config-path PATH         Output mariadb_manager config path (default: /etc/mariadb_backup.conf)
  --backup-root PATH         Base backup directory (default: /var/backups/mariadb)
  --mysql-host HOST          MySQL host for config file (default: localhost)
  --mysql-port PORT          MySQL port for config file (default: 3306)
  --skip-install             Skip package installation and only configure user/service/config
  --skip-config-write        Do not write config file
  --non-interactive          Fail instead of prompting for missing values
  --force                    Overwrite existing config file without prompt
  -h, --help                 Show this help message

Examples:
  sudo ./$SCRIPT_NAME --db-admin-pass 'StrongPass123!'
  sudo ./$SCRIPT_NAME --db-admin-user restore --db-admin-pass 'StrongPass123!' --config-path /root/mariadb_backup.conf
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

warn() {
  printf '[%s] WARNING: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >&2
}

error_exit() {
  printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >&2
  exit 1
}

require_root() {
  if [[ ${EUID} -ne 0 ]]; then
    error_exit "Run as root (use sudo)."
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --db-admin-user)
        DB_ADMIN_USER="$2"
        shift 2
        ;;
      --db-admin-pass)
        DB_ADMIN_PASS="$2"
        shift 2
        ;;
      --db-admin-host)
        DB_ADMIN_HOST="$2"
        shift 2
        ;;
      --config-path)
        CONFIG_PATH="$2"
        shift 2
        ;;
      --backup-root)
        BACKUP_ROOT="$2"
        shift 2
        ;;
      --mysql-host)
        MYSQL_HOST="$2"
        shift 2
        ;;
      --mysql-port)
        MYSQL_PORT="$2"
        shift 2
        ;;
      --skip-install)
        SKIP_INSTALL=1
        shift
        ;;
      --skip-config-write)
        SKIP_CONFIG_WRITE=1
        shift
        ;;
      --non-interactive)
        NON_INTERACTIVE=1
        shift
        ;;
      --force)
        FORCE=1
        shift
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      *)
        error_exit "Unknown option: $1"
        ;;
    esac
  done
}

prompt_for_missing() {
  if [[ -z "$DB_ADMIN_PASS" ]]; then
    if [[ $NON_INTERACTIVE -eq 1 ]]; then
      error_exit "--db-admin-pass is required in non-interactive mode"
    fi

    read -r -s -p "Enter password for '${DB_ADMIN_USER}'@'${DB_ADMIN_HOST}': " DB_ADMIN_PASS
    echo
    [[ -n "$DB_ADMIN_PASS" ]] || error_exit "Password cannot be empty"
  fi
}

validate_inputs() {
  [[ -n "$DB_ADMIN_USER" ]] || error_exit "db admin user cannot be empty"
  [[ -n "$DB_ADMIN_HOST" ]] || error_exit "db admin host cannot be empty"
  [[ -n "$MYSQL_HOST" ]] || error_exit "mysql host cannot be empty"
  [[ -n "$MYSQL_PORT" ]] || error_exit "mysql port cannot be empty"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

install_mariadb() {
  if [[ $SKIP_INSTALL -eq 1 ]]; then
    log "Skipping package installation (--skip-install)"
    return
  fi

  if command_exists apt-get; then
    log "Installing MariaDB with apt-get"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y mariadb-server mariadb-client
  elif command_exists dnf; then
    log "Installing MariaDB with dnf"
    dnf install -y mariadb-server mariadb
  elif command_exists yum; then
    log "Installing MariaDB with yum"
    yum install -y mariadb-server mariadb
  else
    error_exit "Unsupported package manager. Install MariaDB manually and re-run with --skip-install"
  fi
}

start_mariadb_service() {
  local service_name=""

  if systemctl list-unit-files | grep -q '^mariadb\.service'; then
    service_name="mariadb"
  elif systemctl list-unit-files | grep -q '^mysql\.service'; then
    service_name="mysql"
  else
    # Try common default even if list-unit-files is restricted.
    service_name="mariadb"
  fi

  log "Enabling and starting service: ${service_name}"
  systemctl enable --now "$service_name" || {
    if [[ "$service_name" == "mariadb" ]]; then
      service_name="mysql"
      log "Retrying with service: ${service_name}"
      systemctl enable --now "$service_name"
    else
      error_exit "Unable to start MariaDB/MySQL service"
    fi
  }

  # Wait for socket/server readiness.
  local tries=0
  until mysqladmin ping --silent >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [[ $tries -ge 30 ]]; then
      error_exit "MariaDB did not become ready within 30 seconds"
    fi
    sleep 1
  done

  log "MariaDB service is ready"
}

sql_escape() {
  # Escape backslash and single quote for safe SQL string literal.
  printf '%s' "$1" | sed "s/\\\\/\\\\\\\\/g; s/'/''/g"
}

configure_restore_user() {
  local user_esc
  local host_esc
  local pass_esc
  user_esc="$(sql_escape "$DB_ADMIN_USER")"
  host_esc="$(sql_escape "$DB_ADMIN_HOST")"
  pass_esc="$(sql_escape "$DB_ADMIN_PASS")"

  log "Creating/updating MariaDB user '${DB_ADMIN_USER}'@'${DB_ADMIN_HOST}'"
  mysql <<SQL
CREATE USER IF NOT EXISTS '${user_esc}'@'${host_esc}' IDENTIFIED BY '${pass_esc}';
ALTER USER '${user_esc}'@'${host_esc}' IDENTIFIED BY '${pass_esc}';
GRANT ALL PRIVILEGES ON *.* TO '${user_esc}'@'${host_esc}' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SQL

  log "Restore admin user is configured"
}

create_backup_dirs() {
  local hourly daily monthly
  hourly="${BACKUP_ROOT}/hourly"
  daily="${BACKUP_ROOT}/daily"
  monthly="${BACKUP_ROOT}/monthly"

  mkdir -p "$hourly" "$daily" "$monthly"
  log "Backup directories created under ${BACKUP_ROOT}"
}

write_manager_config() {
  if [[ $SKIP_CONFIG_WRITE -eq 1 ]]; then
    log "Skipping config file write (--skip-config-write)"
    return
  fi

  local cfg_dir
  cfg_dir="$(dirname "$CONFIG_PATH")"
  mkdir -p "$cfg_dir"

  if [[ -f "$CONFIG_PATH" && $FORCE -ne 1 && $NON_INTERACTIVE -ne 1 ]]; then
    read -r -p "Config exists at ${CONFIG_PATH}. Overwrite? (y/N): " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
      warn "Keeping existing config file"
      return
    fi
  elif [[ -f "$CONFIG_PATH" && $FORCE -ne 1 && $NON_INTERACTIVE -eq 1 ]]; then
    error_exit "Config exists at ${CONFIG_PATH}. Use --force to overwrite in non-interactive mode"
  fi

  cat > "$CONFIG_PATH" <<EOF
[mysql]
host = ${MYSQL_HOST}
user = ${DB_ADMIN_USER}
password = ${DB_ADMIN_PASS}
port = ${MYSQL_PORT}

[backup_paths]
hourly = ${BACKUP_ROOT}/hourly
daily = ${BACKUP_ROOT}/daily
monthly = ${BACKUP_ROOT}/monthly

[options]
compression = yes
encryption = no
encryption_key_file = /root/.mariadb_backup_key

[rotation]
hourly_keep = 24
daily_keep = 31
monthly_keep = 12

[replication]
master_host =
master_user =
master_password =
master_port = 3306

[webhooks]
success_url =
failure_url =
EOF

  chmod 600 "$CONFIG_PATH"
  log "Config file written: ${CONFIG_PATH}"
}

print_summary() {
  cat <<EOF

Provisioning complete.

MariaDB restore user:
  user: ${DB_ADMIN_USER}
  host: ${DB_ADMIN_HOST}

MariaDB manager config:
  ${CONFIG_PATH}

Next steps:
  1) Test connectivity:
     mysql --host=${MYSQL_HOST} --port=${MYSQL_PORT} --user=${DB_ADMIN_USER} --password='***' -e "SELECT 1;"

  2) Run restore with this config:
     ./mariadb_manager.py --config ${CONFIG_PATH} --restore /path/to/backup --restore-mode full

EOF
}

main() {
  require_root
  parse_args "$@"
  prompt_for_missing
  validate_inputs

  install_mariadb
  start_mariadb_service
  configure_restore_user
  create_backup_dirs
  write_manager_config
  print_summary
}

main "$@"
