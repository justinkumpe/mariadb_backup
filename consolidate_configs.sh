#!/bin/bash

# Helper script to consolidate multiple config files

echo "MariaDB Backup Config Consolidation Helper"
echo "==========================================="
echo ""

# Find all config files
configs=()

if [ -f "/root/mariadb_backup/mariadb_backup.conf" ]; then
    configs+=("/root/mariadb_backup/mariadb_backup.conf")
fi

if [ -f "/etc/mariadb_backup.conf" ]; then
    configs+=("/etc/mariadb_backup.conf")
fi

if [ -f "$HOME/.config/mariadb_backup.conf" ]; then
    configs+=("$HOME/.config/mariadb_backup.conf")
fi

if [ -f "mariadb_backup.conf" ]; then
    abs_path=$(readlink -f "mariadb_backup.conf")
    configs+=("$abs_path")
fi

# Remove duplicates
configs=($(printf "%s\n" "${configs[@]}" | sort -u))

if [ ${#configs[@]} -eq 0 ]; then
    echo "No config files found."
    exit 0
fi

if [ ${#configs[@]} -eq 1 ]; then
    echo "Only one config file found:"
    echo "  ${configs[0]}"
    echo ""
    echo "✓ No consolidation needed!"
    exit 0
fi

echo "Found ${#configs[@]} config files:"
echo ""

# Show details of each
for i in "${!configs[@]}"; do
    config="${configs[$i]}"
    echo "$((i+1)). $config"
    
    if [ -f "$config" ]; then
        size=$(stat -c%s "$config" 2>/dev/null || stat -f%z "$config" 2>/dev/null)
        mtime=$(stat -c%y "$config" 2>/dev/null || stat -f%Sm "$config" 2>/dev/null)
        echo "   Size: $size bytes"
        echo "   Modified: $mtime"
        
        # Extract key info
        if grep -q "^password = .\+" "$config" 2>/dev/null; then
            echo "   Password: SET"
        else
            echo "   Password: (empty)"
        fi
        
        user=$(grep "^user = " "$config" | cut -d= -f2 | xargs)
        if [ -n "$user" ]; then
            echo "   User: $user"
        fi
    fi
    echo ""
done

echo "==========================================="
echo ""
echo "Which config file do you want to KEEP and use?"
read -p "Enter number (1-${#configs[@]}): " choice

if [[ ! "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#configs[@]}" ]; then
    echo "Invalid choice"
    exit 1
fi

keep_config="${configs[$((choice-1))]}"

echo ""
echo "You chose to keep: $keep_config"
echo ""
echo "The following files will be BACKED UP and REMOVED:"
for i in "${!configs[@]}"; do
    if [ $i -ne $((choice-1)) ]; then
        echo "  ${configs[$i]}"
    fi
done

echo ""
read -p "Proceed? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

# Backup and remove other configs
for i in "${!configs[@]}"; do
    if [ $i -ne $((choice-1)) ]; then
        config="${configs[$i]}"
        backup="${config}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$config" "$backup"
        echo "✓ Backed up $config to $backup"
        rm "$config"
        echo "✓ Removed $config"
    fi
done

echo ""
echo "==========================================="
echo "✓ Consolidation complete!"
echo ""
echo "Active config: $keep_config"
echo ""
echo "From now on, always run with:"
echo "  ./mariadb_manager.py --config $keep_config"
echo ""
echo "Or create an alias:"
echo "  alias mariadb-backup='$PWD/mariadb_manager.py --config $keep_config'"
