#!/usr/bin/env python3

"""
Test the multi-config detection
"""

import os
import sys
import shutil

# Setup test environment with multiple configs
os.makedirs('test_multiconfig', exist_ok=True)
os.chdir('test_multiconfig')

# Create multiple config files like the user has
config1 = 'mariadb_backup.conf'
config2 = os.path.expanduser('~/.config/mariadb_backup.conf')

# Create config 1 (current directory)
with open(config1, 'w') as f:
    f.write("""[mysql]
host = localhost
user = root
password = 
port = 3306

[backup_paths]
hourly = /var/backups/mariadb/hourly
daily = /var/backups/mariadb/daily
monthly = /var/backups/mariadb/monthly

[options]
compression = yes
""")

# Create config 2 (~/.config)
os.makedirs(os.path.dirname(config2), exist_ok=True)
with open(config2, 'w') as f:
    f.write("""[mysql]
host = localhost
user = justinkumpe
password = mypassword123456
port = 3306

[backup_paths]
hourly = /var/backups/mariadb/hourly
daily = /var/backups/mariadb/daily
monthly = /var/backups/mariadb/monthly

[options]
compression = yes
""")

print("Created two config files:")
print(f"  1. {os.path.abspath(config1)}")
print(f"  2. {config2}")
print()

# Now test the manager
sys.path.insert(0, '..')
from mariadb_manager import MariaDBManager

print("Creating MariaDBManager with no config specified...")
print()
manager = MariaDBManager()

print()
print(f"Manager is using: {manager.config_file}")
print(f"MySQL user: {manager.config['mysql']['user']}")
print(f"MySQL password: {manager.config['mysql']['password']}")

# Cleanup
os.chdir('..')
shutil.rmtree('test_multiconfig')
