#!/usr/bin/env python3

"""
Test config write functionality
"""

import configparser
import os

config_file = 'test_config.conf'

print("Testing ConfigParser write operations...\n")

# Create a new config
config = configparser.ConfigParser()

# Add sections and set values using .set()
config.add_section('mysql')
config.set('mysql', 'host', 'testhost')
config.set('mysql', 'user', 'testuser')
config.set('mysql', 'password', 'testpass')
config.set('mysql', 'port', '3307')

# Write to file
with open(config_file, 'w') as f:
    config.write(f)

print(f"✓ Created {config_file}")

# Read it back
config2 = configparser.ConfigParser()
config2.read(config_file)

print(f"✓ Read back {config_file}\n")
print("Values read:")
print(f"  host: {config2['mysql']['host']}")
print(f"  user: {config2['mysql']['user']}")
print(f"  password: {config2['mysql']['password']}")
print(f"  port: {config2['mysql']['port']}")

# Verify
if (config2['mysql']['host'] == 'testhost' and
    config2['mysql']['user'] == 'testuser' and
    config2['mysql']['password'] == 'testpass' and
    config2['mysql']['port'] == '3307'):
    print("\n✓ All values match! Config write/read works correctly.")
else:
    print("\n✗ Values don't match! There's a problem.")

# Cleanup
os.remove(config_file)
print(f"\n✓ Cleaned up {config_file}")
