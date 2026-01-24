#!/usr/bin/env python3

"""
Test the config save/load workflow
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mariadb_manager import MariaDBManager

print("Testing MariaDB Manager config workflow...\n")

# Clean up any existing test config
test_config = 'test_workflow.conf'
if os.path.exists(test_config):
    os.remove(test_config)

print("Step 1: Create new instance (should create default config)")
manager = MariaDBManager(test_config)

if os.path.exists(test_config):
    print(f"✓ Config file created: {test_config}\n")
else:
    print(f"✗ Config file NOT created!\n")
    sys.exit(1)

print("Step 2: Modify configuration")
manager.config.set('mysql', 'host', 'testhost')
manager.config.set('mysql', 'user', 'testuser')
manager.config.set('mysql', 'password', 'testpassword')
manager.config.set('mysql', 'port', '3307')
print("✓ Values modified in memory\n")

print("Step 3: Save configuration")
if manager.save_config():
    print(f"✓ Configuration saved\n")
else:
    print(f"✗ Save failed!\n")
    sys.exit(1)

print("Step 4: Create new instance to reload config")
manager2 = MariaDBManager(test_config)

print("Step 5: Verify loaded values")
errors = []

if manager2.config['mysql']['host'] != 'testhost':
    errors.append(f"host: expected 'testhost', got '{manager2.config['mysql']['host']}'")
if manager2.config['mysql']['user'] != 'testuser':
    errors.append(f"user: expected 'testuser', got '{manager2.config['mysql']['user']}'")
if manager2.config['mysql']['password'] != 'testpassword':
    errors.append(f"password: expected 'testpassword', got '{manager2.config['mysql']['password']}'")
if manager2.config['mysql']['port'] != '3307':
    errors.append(f"port: expected '3307', got '{manager2.config['mysql']['port']}'")

if errors:
    print("✗ Verification FAILED:")
    for error in errors:
        print(f"  - {error}")
    print()
else:
    print("✓ All values match!\n")

print("Step 6: Display config file contents")
with open(test_config, 'r') as f:
    print("---")
    print(f.read())
    print("---\n")

# Cleanup
os.remove(test_config)
print(f"✓ Cleaned up {test_config}\n")

if errors:
    print("❌ TEST FAILED")
    sys.exit(1)
else:
    print("✅ TEST PASSED - Config save/load works correctly!")
    sys.exit(0)
