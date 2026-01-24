#!/usr/bin/env python3

"""
Quick test to verify config file read/write
"""

import configparser
import os

config_file = 'mariadb_backup.conf'

print("Testing config file operations...")
print(f"Config file: {config_file}")
print()

# Test 1: Check if file exists
if os.path.exists(config_file):
    print(f"✓ Config file exists")
    
    # Test 2: Read the file
    config = configparser.ConfigParser()
    config.read(config_file)
    
    print(f"✓ Config file loaded")
    print()
    
    # Test 3: Display sections
    print("Sections found:")
    for section in config.sections():
        print(f"  [{section}]")
        for key, value in config.items(section):
            if key == 'password' and value:
                print(f"    {key} = {'*' * len(value)}")
            else:
                print(f"    {key} = {value}")
        print()
    
    # Test 4: Check required fields
    print("Required fields check:")
    required = {
        'mysql': ['host', 'user', 'password', 'port'],
        'backup_paths': ['hourly', 'daily', 'monthly'],
        'options': ['compression']
    }
    
    all_good = True
    for section, keys in required.items():
        if not config.has_section(section):
            print(f"  ✗ Missing section: [{section}]")
            all_good = False
        else:
            for key in keys:
                if not config.has_option(section, key):
                    print(f"  ✗ Missing key: {section}.{key}")
                    all_good = False
                else:
                    value = config.get(section, key)
                    if key == 'password':
                        status = "set" if value else "empty"
                        print(f"  ✓ {section}.{key} = {status}")
                    else:
                        print(f"  ✓ {section}.{key} = {value}")
    
    if all_good:
        print("\n✓ All required fields present")
    else:
        print("\n✗ Some fields missing")
    
    # Test 5: Check file permissions
    import stat
    mode = oct(os.stat(config_file).st_mode)[-3:]
    print(f"\nFile permissions: {mode}")
    if mode == '600':
        print("✓ Permissions are secure (600)")
    else:
        print(f"⚠ Warning: Permissions should be 600, not {mode}")
        print("  Fix with: chmod 600 mariadb_backup.conf")
    
else:
    print(f"✗ Config file not found: {config_file}")
    print("  Run ./mariadb_manager.py first to create it")
    print("  Or copy from example: cp mariadb_backup.conf.example mariadb_backup.conf")
