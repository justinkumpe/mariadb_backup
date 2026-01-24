#!/bin/bash

# Installation script for MariaDB Manager

echo "======================================"
echo "MariaDB Backup Manager - Installation"
echo "======================================"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be run as root for system-wide installation"
   echo "Continue anyway? (y/n)"
   read -r response
   if [[ ! "$response" =~ ^[Yy]$ ]]; then
       exit 1
   fi
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed"
    echo "Install with: apt-get install python3 (Debian/Ubuntu)"
    echo "           or: yum install python3 (RHEL/CentOS)"
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"

# Check for required MySQL commands
echo ""
echo "Checking for required commands..."

for cmd in mysql mysqldump; do
    if command -v $cmd &> /dev/null; then
        echo "✓ $cmd found"
    else
        echo "✗ $cmd not found"
        echo "  Install MariaDB client: apt-get install mariadb-client"
        exit 1
    fi
done

# Optional but recommended commands
for cmd in gzip; do
    if command -v $cmd &> /dev/null; then
        echo "✓ $cmd found"
    else
        echo "⚠  $cmd not found (optional, but recommended for compression)"
    fi
done

echo ""
echo "Installation options:"
echo "1. Install to /usr/local/bin (system-wide, requires root)"
echo "2. Install to ~/bin (current user only)"
echo "3. Skip installation (just configure)"
echo ""
read -p "Select option (1-3): " install_option

INSTALL_DIR=""
CONFIG_DIR=""

case $install_option in
    1)
        INSTALL_DIR="/usr/local/bin"
        CONFIG_DIR="/etc"
        ;;
    2)
        INSTALL_DIR="$HOME/bin"
        CONFIG_DIR="$HOME/.config"
        mkdir -p "$INSTALL_DIR"
        mkdir -p "$CONFIG_DIR"
        ;;
    3)
        INSTALL_DIR="."
        CONFIG_DIR="."
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

# Copy main script
if [ "$INSTALL_DIR" != "." ]; then
    echo ""
    echo "Installing script to $INSTALL_DIR..."
    cp mariadb_manager.py "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/mariadb_manager.py"
    echo "✓ Script installed"
fi

# Setup configuration
echo ""
echo "Setting up configuration..."

CONFIG_FILE="$CONFIG_DIR/mariadb_backup.conf"

if [ -f "$CONFIG_FILE" ]; then
    echo "Configuration file already exists: $CONFIG_FILE"
    read -p "Overwrite? (y/n): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Keeping existing configuration"
    else
        cp mariadb_backup.conf.example "$CONFIG_FILE"
        chmod 600 "$CONFIG_FILE"
        echo "✓ Configuration file created"
    fi
else
    cp mariadb_backup.conf.example "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    echo "✓ Configuration file created: $CONFIG_FILE"
fi

# Configure MySQL credentials
echo ""
echo "Configure MySQL connection? (y/n)"
read -p "> " configure_mysql

if [[ "$configure_mysql" =~ ^[Yy]$ ]]; then
    read -p "MySQL Host [localhost]: " mysql_host
    mysql_host=${mysql_host:-localhost}
    
    read -p "MySQL Port [3306]: " mysql_port
    mysql_port=${mysql_port:-3306}
    
    read -p "MySQL User [root]: " mysql_user
    mysql_user=${mysql_user:-root}
    
    read -sp "MySQL Password: " mysql_password
    echo ""
    
    # Update config file
    if command -v sed &> /dev/null; then
        sed -i.bak "s/^host = .*/host = $mysql_host/" "$CONFIG_FILE"
        sed -i.bak "s/^port = .*/port = $mysql_port/" "$CONFIG_FILE"
        sed -i.bak "s/^user = .*/user = $mysql_user/" "$CONFIG_FILE"
        sed -i.bak "s/^password = .*/password = $mysql_password/" "$CONFIG_FILE"
        rm -f "$CONFIG_FILE.bak"
        echo "✓ MySQL credentials configured"
    fi
fi

# Setup backup directories
echo ""
echo "Configure backup directories? (y/n)"
read -p "> " configure_dirs

if [[ "$configure_dirs" =~ ^[Yy]$ ]]; then
    read -p "Hourly backup path [/var/backups/mariadb/hourly]: " hourly_path
    hourly_path=${hourly_path:-/var/backups/mariadb/hourly}
    
    read -p "Daily backup path [/var/backups/mariadb/daily]: " daily_path
    daily_path=${daily_path:-/var/backups/mariadb/daily}
    
    read -p "Monthly backup path [/var/backups/mariadb/monthly]: " monthly_path
    monthly_path=${monthly_path:-/var/backups/mariadb/monthly}
    
    # Create directories
    mkdir -p "$hourly_path" "$daily_path" "$monthly_path" 2>/dev/null
    
    # Update config
    if command -v sed &> /dev/null; then
        sed -i.bak "s|^hourly = .*|hourly = $hourly_path|" "$CONFIG_FILE"
        sed -i.bak "s|^daily = .*|daily = $daily_path|" "$CONFIG_FILE"
        sed -i.bak "s|^monthly = .*|monthly = $monthly_path|" "$CONFIG_FILE"
        rm -f "$CONFIG_FILE.bak"
        echo "✓ Backup directories configured"
    fi
fi

# Test connection
echo ""
echo "Test MySQL connection? (y/n)"
read -p "> " test_conn

if [[ "$test_conn" =~ ^[Yy]$ ]]; then
    if [ "$INSTALL_DIR" = "." ]; then
        python3 mariadb_manager.py --config "$CONFIG_FILE" --list > /dev/null 2>&1
    else
        "$INSTALL_DIR/mariadb_manager.py" --config "$CONFIG_FILE" --list > /dev/null 2>&1
    fi
    
    if [ $? -eq 0 ]; then
        echo "✓ Connection test successful!"
    else
        echo "✗ Connection test failed. Please check your credentials."
    fi
fi

echo ""
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""

if [ "$INSTALL_DIR" != "." ]; then
    echo "Script location: $INSTALL_DIR/mariadb_manager.py"
fi
echo "Config location: $CONFIG_FILE"
echo ""
echo "Usage:"
if [ "$INSTALL_DIR" != "." ]; then
    echo "  $INSTALL_DIR/mariadb_manager.py                    # Interactive menu"
    echo "  $INSTALL_DIR/mariadb_manager.py --backup daily     # Create backup"
    echo "  $INSTALL_DIR/mariadb_manager.py --list             # List backups"
else
    echo "  ./mariadb_manager.py                    # Interactive menu"
    echo "  ./mariadb_manager.py --backup daily     # Create backup"
    echo "  ./mariadb_manager.py --list             # List backups"
fi
echo ""
echo "For full documentation, see README.md"
echo ""

# Offer to setup cron
if [[ $EUID -eq 0 ]] || [ "$INSTALL_DIR" = "$HOME/bin" ]; then
    echo "Would you like to setup automated backups (cron)? (y/n)"
    read -p "> " setup_cron
    
    if [[ "$setup_cron" =~ ^[Yy]$ ]]; then
        CRON_SCRIPT="$INSTALL_DIR/mariadb_manager.py"
        
        echo ""
        echo "Select backup schedule:"
        echo "1. Hourly + Daily + Monthly (recommended)"
        echo "2. Daily only"
        echo "3. Daily + Monthly"
        read -p "Option (1-3): " cron_option
        
        CRON_ENTRIES=""
        
        case $cron_option in
            1)
                CRON_ENTRIES="# MariaDB Hourly Backup
0 * * * * $CRON_SCRIPT --backup hourly --config $CONFIG_FILE >> /var/log/mariadb_backup.log 2>&1

# MariaDB Daily Backup (2 AM)
0 2 * * * $CRON_SCRIPT --backup daily --config $CONFIG_FILE >> /var/log/mariadb_backup.log 2>&1

# MariaDB Monthly Backup (1st of month, 3 AM)
0 3 1 * * $CRON_SCRIPT --backup monthly --config $CONFIG_FILE >> /var/log/mariadb_backup.log 2>&1"
                ;;
            2)
                CRON_ENTRIES="# MariaDB Daily Backup (2 AM)
0 2 * * * $CRON_SCRIPT --backup daily --config $CONFIG_FILE >> /var/log/mariadb_backup.log 2>&1"
                ;;
            3)
                CRON_ENTRIES="# MariaDB Daily Backup (2 AM)
0 2 * * * $CRON_SCRIPT --backup daily --config $CONFIG_FILE >> /var/log/mariadb_backup.log 2>&1

# MariaDB Monthly Backup (1st of month, 3 AM)
0 3 1 * * $CRON_SCRIPT --backup monthly --config $CONFIG_FILE >> /var/log/mariadb_backup.log 2>&1"
                ;;
        esac
        
        echo ""
        echo "The following will be added to crontab:"
        echo "----------------------------------------"
        echo "$CRON_ENTRIES"
        echo "----------------------------------------"
        echo ""
        read -p "Proceed? (y/n): " proceed_cron
        
        if [[ "$proceed_cron" =~ ^[Yy]$ ]]; then
            (crontab -l 2>/dev/null; echo "$CRON_ENTRIES") | crontab -
            echo "✓ Cron jobs installed"
            echo ""
            echo "View cron jobs with: crontab -l"
        fi
    fi
fi

echo ""
echo "Setup complete! Happy backing up! 🚀"
