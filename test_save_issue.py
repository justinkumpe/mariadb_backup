#!/usr/bin/env python3

"""
Simulate the configure and save process
"""

import os
import configparser

config_file = 'test_save_issue.conf'

print("Simulating the config save issue...")
print()

# Step 1: Create initial config (like first run)
print("1. Creating initial config file...")
config = configparser.ConfigParser()
config.add_section('mysql')
config.set('mysql', 'host', 'localhost')
config.set('mysql', 'user', 'root')
config.set('mysql', 'password', '')
config.set('mysql', 'port', '3306')

with open(config_file, 'w') as f:
    config.write(f)
os.chmod(config_file, 0o600)
print(f"   Created: {config_file}")
print()

# Step 2: Read the config back (like loading in menu)
print("2. Loading config file (simulating menu load)...")
config2 = configparser.ConfigParser()
config2.read(config_file)
print(f"   Loaded. Current host: {config2['mysql']['host']}")
print()

# Step 3: Modify values (like user entering new values)
print("3. Modifying values (simulating user input)...")
config2.set('mysql', 'host', 'newhost')
config2.set('mysql', 'user', 'newuser')
config2.set('mysql', 'password', 'newpass')
config2.set('mysql', 'port', '3307')
print(f"   Modified in memory. host now: {config2['mysql']['host']}")
print()

# Step 4: Save the config (like choosing "Save and Exit")
print("4. Saving config file...")
with open(config_file, 'w') as f:
    config2.write(f)
os.chmod(config_file, 0o600)
print(f"   Saved to: {config_file}")
print()

# Step 5: Read back again (like next run)
print("5. Reading config file again (simulating next run)...")
config3 = configparser.ConfigParser()
config3.read(config_file)
print(f"   Loaded. host is: {config3['mysql']['host']}")
print(f"   user is: {config3['mysql']['user']}")
print(f"   password is: {config3['mysql']['password']}")
print(f"   port is: {config3['mysql']['port']}")
print()

# Step 6: Show file contents
print("6. Actual file contents:")
print("-" * 40)
with open(config_file, 'r') as f:
    print(f.read())
print("-" * 40)
print()

# Verify
if config3['mysql']['host'] == 'newhost':
    print("✅ SUCCESS: Values were saved and loaded correctly!")
else:
    print("❌ FAILURE: Values were NOT saved correctly!")
    print(f"   Expected: newhost")
    print(f"   Got: {config3['mysql']['host']}")

# Cleanup
os.remove(config_file)
