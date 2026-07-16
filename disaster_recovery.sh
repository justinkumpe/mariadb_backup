#!/bin/bash

# Disaster recovery bootstrap for MariaDB servers that will not start or have broken credentials.
# Wraps mariadb_manager.py disaster recovery mode.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANAGER_SCRIPT="${SCRIPT_DIR}/mariadb_manager.py"
CONFIG_PATH=""
DB_ADMIN_USER=""
DB_ADMIN_PASS=""
DB_ADMIN_HOST="localhost"
ROOT_PASS=""
RESET_SYSTEM_TABLES=0
RESTORE_PATH=""
RESTORE_MODE="full"
NON_INTERACTIVE=0
SKIP_CONFIRM=0
MANAGER_CMD=()

print_usage() {
  cat <<EOF
Usage: sudo $0 [options]

Recover a MariaDB server when the service will not start or restore credentials are broken.
This script diagnoses the server, optionally rebuilds mysql system tables, creates a restore
admin user, updates mariadb_backup.conf, and can chain into a backup restore.

Options:
  --config-path PATH           mariadb_manager config path (optional)
  --db-admin-user USER         Restore admin user (default: restore_admin or config user)
  --db-admin-pass PASS         Restore admin password (required unless interactive)
  --db-admin-host HOST         Restore admin host part (default: localhost)
  --root-pass PASS             Optional new MariaDB root@localhost password
  --reset-mysql-system-tables  Rebuild mysql system schema files (preserves app databases)
  --restore-path PATH          Restore this backup after recovery completes
  --restore-mode MODE          Restore mode: full, users-grants, databases, schema, data
  --non-interactive            Fail instead of prompting for missing values
  --yes                        Skip confirmation prompts
  -h, --help                   Show this help message

Examples:
  sudo ./$0 --db-admin-pass 'StrongPass123!'
  sudo ./$0 --reset-mysql-system-tables --db-admin-pass 'StrongPass123!' --yes
  sudo ./$0 --db-admin-pass 'StrongPass123!' --restore-path /var/backups/mariadb/daily/backup_daily_20250701
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
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
      --config-path)
        CONFIG_PATH="$2"
        shift 2
        ;;
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
      --root-pass)
        ROOT_PASS="$2"
        shift 2
        ;;
      --reset-mysql-system-tables)
        RESET_SYSTEM_TABLES=1
        shift
        ;;
      --restore-path)
        RESTORE_PATH="$2"
        shift 2
        ;;
      --restore-mode)
        RESTORE_MODE="$2"
        shift 2
        ;;
      --non-interactive)
        NON_INTERACTIVE=1
        shift
        ;;
      --yes)
        SKIP_CONFIRM=1
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

validate_inputs() {
  if [[ ! -f "$MANAGER_SCRIPT" ]]; then
    error_exit "mariadb_manager.py not found at ${MANAGER_SCRIPT}"
  fi

  if [[ -z "$DB_ADMIN_PASS" && $NON_INTERACTIVE -eq 1 ]]; then
    error_exit "--db-admin-pass is required in non-interactive mode"
  fi
}

build_manager_command() {
  MANAGER_CMD=(python3 "$MANAGER_SCRIPT" --disaster-recovery)

  if [[ -n "$CONFIG_PATH" ]]; then
    MANAGER_CMD+=(--config "$CONFIG_PATH")
  fi
  if [[ -n "$DB_ADMIN_USER" ]]; then
    MANAGER_CMD+=(--dr-admin-user "$DB_ADMIN_USER")
  fi
  if [[ -n "$DB_ADMIN_PASS" ]]; then
    MANAGER_CMD+=(--dr-admin-pass "$DB_ADMIN_PASS")
  fi
  if [[ -n "$DB_ADMIN_HOST" ]]; then
    MANAGER_CMD+=(--dr-admin-host "$DB_ADMIN_HOST")
  fi
  if [[ -n "$ROOT_PASS" ]]; then
    MANAGER_CMD+=(--dr-root-pass "$ROOT_PASS")
  fi
  if [[ $RESET_SYSTEM_TABLES -eq 1 ]]; then
    MANAGER_CMD+=(--reset-mysql-system-tables)
  fi
  if [[ $SKIP_CONFIRM -eq 1 ]]; then
    MANAGER_CMD+=(--dr-yes)
  fi
  if [[ -n "$RESTORE_PATH" ]]; then
    MANAGER_CMD+=(--restore "$RESTORE_PATH" --restore-mode "$RESTORE_MODE")
  fi
}

main() {
  require_root
  parse_args "$@"
  validate_inputs

  log "Starting MariaDB disaster recovery"
  build_manager_command
  "${MANAGER_CMD[@]}"
}

main "$@"
