#!/usr/bin/env python3

"""
Test that exactly simulates user workflow:
1. Run script first time (creates config)
2. Go to settings menu
3. Change values  
4. Save and exit
5. Run script again
6. Verify values persisted
"""

import os
import sys
import subprocess
import time

# Clean up any existing test config
test_config = 'test_user_workflow.conf'
if os.path.exists(test_config):
    os.remove(test_config)

print("=" * 60)
print("Simulating exact user workflow")
print("=" * 60)

# Step 1: Create a Python script that will modify and save config
test_script = """
import sys
sys.path.insert(0, '.')
from mariadb_manager import MariaDBManager

print("\\nStep 1: Creating manager instance")
manager = MariaDBManager('test_user_workflow.conf')

print("\\nStep 2: Current values:")
print(f"  host: {manager.config['mysql']['host']}")
print(f"  user: {manager.config['mysql']['user']}")
print(f"  password: {manager.config['mysql']['password']}")

print("\\nStep 3: Modifying values")
manager.config.set('mysql', 'host', 'modified_host')
manager.config.set('mysql', 'user', 'modified_user')
manager.config.set('mysql', 'password', 'modified_password')

print("\\nStep 4: Values after modification:")
print(f"  host: {manager.config['mysql']['host']}")
print(f"  user: {manager.config['mysql']['user']}")
print(f"  password: {manager.config['mysql']['password']}")

print("\\nStep 5: Saving config")
result = manager.save_config()
print(f"Save result: {result}")

print("\\nStep 6: Exiting (simulating script end)")
"""

# Write and run the test script
with open('_test_modify.py', 'w') as f:
    f.write(test_script)

print("\n" + "=" * 60)
print("FIRST RUN: Creating and modifying config")
print("=" * 60)
result = subprocess.run([sys.executable, '_test_modify.py'], cwd=os.getcwd())

if result.returncode != 0:
    print("\n❌ First run failed!")
    sys.exit(1)

# Give filesystem time to sync
time.sleep(0.5)

# Now verify the file
print("\n" + "=" * 60)
print("VERIFICATION: Checking saved file")
print("=" * 60)

if not os.path.exists(test_config):
    print(f"\n❌ Config file doesn't exist: {test_config}")
    sys.exit(1)

print(f"\n✓ Config file exists: {test_config}")
print(f"  Size: {os.path.getsize(test_config)} bytes")

# Read and display file contents
print("\nFile contents:")
print("-" * 60)
with open(test_config, 'r') as f:
    contents = f.read()
    print(contents)
print("-" * 60)

# Step 2: Load config again (simulating second run)
verify_script = """
import sys
sys.path.insert(0, '.')
from mariadb_manager import MariaDBManager

print("\\nLoading config (simulating second run)")
manager = MariaDBManager('test_user_workflow.conf')

print("\\nValues loaded:")
print(f"  host: {manager.config['mysql']['host']}")
print(f"  user: {manager.config['mysql']['user']}")
print(f"  password: {manager.config['mysql']['password']}")

# Verify
errors = []
if manager.config['mysql']['host'] != 'modified_host':
    errors.append(f"host: expected 'modified_host', got '{manager.config['mysql']['host']}'")
if manager.config['mysql']['user'] != 'modified_user':
    errors.append(f"user: expected 'modified_user', got '{manager.config['mysql']['user']}'")
if manager.config['mysql']['password'] != 'modified_password':
    errors.append(f"password: expected 'modified_password', got '{manager.config['mysql']['password']}'")

if errors:
    print("\\n❌ VERIFICATION FAILED:")
    for error in errors:
        print(f"  {error}")
    sys.exit(1)
else:
    print("\\n✅ All values match!")
"""

with open('_test_verify.py', 'w') as f:
    f.write(verify_script)

print("\n" + "=" * 60)
print("SECOND RUN: Loading and verifying config")
print("=" * 60)
result = subprocess.run([sys.executable, '_test_verify.py'], cwd=os.getcwd())

# Cleanup
os.remove('_test_modify.py')
os.remove('_test_verify.py')
if os.path.exists(test_config):
    os.remove(test_config)

if result.returncode == 0:
    print("\n" + "=" * 60)
    print("✅ WORKFLOW TEST PASSED")
    print("=" * 60)
    print("\nConfig save/load cycle works correctly!")
    print("\nIf your actual config is not saving, the issue is:")
    print("1. You're editing a different config file than the one being read")
    print("2. File permissions prevent writing")
    print("3. Running from different directories")
    print("\nRun: ./check_config_location.py to diagnose")
else:
    print("\n" + "=" * 60)
    print("❌ WORKFLOW TEST FAILED")
    print("=" * 60)
    sys.exit(1)
