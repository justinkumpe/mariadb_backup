#!/usr/bin/env python3

"""
Debug utility to check config file status
"""

import os
import sys
import configparser

# Check common locations
config_locations = [
    'mariadb_backup.conf',
    '/etc/mariadb_backup.conf',
    os.path.expanduser('~/.config/mariadb_backup.conf'),
]

print("MariaDB Backup Config File Checker")
print("=" * 60)

for loc in config_locations:
    abs_loc = os.path.abspath(loc)
    print(f"\nChecking: {abs_loc}")
    
    if os.path.exists(loc):
        print(f"  ✓ EXISTS")
        
        # Check permissions
        stat_info = os.stat(loc)
        mode = oct(stat_info.st_mode)[-3:]
        print(f"  Permissions: {mode}")
        
        # Check size
        size = os.path.getsize(loc)
        print(f"  Size: {size} bytes")
        
        # Check modification time
        import datetime
        mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime)
        print(f"  Modified: {mtime}")
        
        # Try to read it
        try:
            config = configparser.ConfigParser()
            config.read(loc)
            print(f"  Sections: {', '.join(config.sections())}")
            
            if config.has_section('mysql'):
                print(f"  MySQL user: {config.get('mysql', 'user', fallback='(not set)')}")
                print(f"  MySQL host: {config.get('mysql', 'host', fallback='(not set)')}")
                pwd = config.get('mysql', 'password', fallback='')
                print(f"  MySQL password: {'set (' + str(len(pwd)) + ' chars)' if pwd else '(empty)'}")
        except Exception as e:
            print(f"  ERROR reading: {e}")
    else:
        print(f"  ✗ NOT FOUND")

print("\n" + "=" * 60)
print("\nCurrent working directory:", os.getcwd())
print("\nIf you run mariadb_manager.py with no arguments,")
print("it will use: " + os.path.abspath('mariadb_backup.conf'))
