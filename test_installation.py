#!/usr/bin/env python3

"""
Test script to verify MariaDB Manager installation and configuration
"""

import os
import sys
import subprocess
import configparser

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_success(text):
    print(f"✓ {text}")

def print_error(text):
    print(f"✗ {text}")

def print_warning(text):
    print(f"⚠  {text}")

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 6:
        print_success(f"Python version: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python 3.6+ required, found {version.major}.{version.minor}.{version.micro}")
        return False

def check_command(cmd):
    """Check if a command exists"""
    try:
        subprocess.run(['which', cmd], capture_output=True, check=True)
        print_success(f"{cmd} is installed")
        return True
    except:
        print_error(f"{cmd} is not installed")
        return False

def check_file_exists(filepath, description):
    """Check if a file exists"""
    if os.path.exists(filepath):
        print_success(f"{description} exists: {filepath}")
        return True
    else:
        print_error(f"{description} not found: {filepath}")
        return False

def check_file_permissions(filepath, expected_mode):
    """Check file permissions"""
    if not os.path.exists(filepath):
        return False
    
    mode = oct(os.stat(filepath).st_mode)[-3:]
    if mode == expected_mode:
        print_success(f"Correct permissions ({mode}) on {filepath}")
        return True
    else:
        print_warning(f"Insecure permissions ({mode}) on {filepath}, should be {expected_mode}")
        return False

def check_config_file(config_file):
    """Check configuration file"""
    if not os.path.exists(config_file):
        print_error(f"Config file not found: {config_file}")
        return False
    
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        
        # Check required sections
        required_sections = ['mysql', 'backup_paths', 'options']
        for section in required_sections:
            if config.has_section(section):
                print_success(f"Config section [{section}] present")
            else:
                print_error(f"Config section [{section}] missing")
                return False
        
        # Check MySQL credentials
        if config['mysql']['user']:
            print_success(f"MySQL user configured: {config['mysql']['user']}")
        else:
            print_warning("MySQL user not configured")
        
        if config['mysql']['password']:
            print_success("MySQL password configured (not empty)")
        else:
            print_warning("MySQL password not configured")
        
        # Check backup paths
        for backup_type in ['hourly', 'daily', 'monthly']:
            path = config['backup_paths'].get(backup_type)
            if path:
                print_success(f"Backup path for {backup_type}: {path}")
                if not os.path.exists(path):
                    print_warning(f"  Path does not exist yet: {path}")
            else:
                print_error(f"Backup path for {backup_type} not configured")
        
        return True
        
    except Exception as e:
        print_error(f"Error reading config: {e}")
        return False

def test_mysql_connection(config_file):
    """Test MySQL connection"""
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        
        cmd = [
            'mysql',
            f"--host={config['mysql']['host']}",
            f"--user={config['mysql']['user']}",
            f"--password={config['mysql']['password']}",
            f"--port={config['mysql']['port']}",
            '-e', 'SELECT VERSION();'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[1] if len(result.stdout.strip().split('\n')) > 1 else 'Unknown'
            print_success(f"MySQL connection successful - Version: {version}")
            return True
        else:
            print_error(f"MySQL connection failed: {result.stderr}")
            return False
            
    except Exception as e:
        print_error(f"MySQL connection test failed: {e}")
        return False

def check_disk_space(paths):
    """Check disk space for backup locations"""
    for path in paths:
        if os.path.exists(path):
            try:
                stat = os.statvfs(path)
                free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
                percent_free = (free_gb / total_gb) * 100
                
                if percent_free > 20:
                    print_success(f"{path}: {free_gb:.1f}GB free ({percent_free:.1f}%)")
                elif percent_free > 10:
                    print_warning(f"{path}: {free_gb:.1f}GB free ({percent_free:.1f}%) - Getting low")
                else:
                    print_error(f"{path}: {free_gb:.1f}GB free ({percent_free:.1f}%) - CRITICAL")
            except:
                pass

def main():
    print_header("MariaDB Backup Manager - Installation Test")
    
    # Check if script is being run from correct directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    manager_script = os.path.join(script_dir, 'mariadb_manager.py')
    
    all_tests_passed = True
    
    # Test 1: Python version
    print_header("Test 1: Python Environment")
    if not check_python_version():
        all_tests_passed = False
    
    # Test 2: Required commands
    print_header("Test 2: Required Commands")
    required_commands = ['mysql', 'mysqldump', 'gzip']
    for cmd in required_commands:
        if not check_command(cmd):
            all_tests_passed = False
    
    # Test 3: Script files
    print_header("Test 3: Script Files")
    if not check_file_exists(manager_script, "Main script"):
        all_tests_passed = False
    
    if os.path.exists(manager_script):
        if os.access(manager_script, os.X_OK):
            print_success("Main script is executable")
        else:
            print_warning("Main script is not executable (run: chmod +x mariadb_manager.py)")
    
    # Test 4: Configuration file
    print_header("Test 4: Configuration File")
    config_locations = [
        'mariadb_backup.conf',
        '/etc/mariadb_backup.conf',
        os.path.expanduser('~/.config/mariadb_backup.conf')
    ]
    
    config_found = False
    config_file = None
    for loc in config_locations:
        if os.path.exists(loc):
            config_file = loc
            config_found = True
            print_success(f"Config file found: {loc}")
            
            # Check permissions
            check_file_permissions(loc, '600')
            
            # Check contents
            check_config_file(loc)
            break
    
    if not config_found:
        print_error("No configuration file found")
        print(f"  Checked locations: {', '.join(config_locations)}")
        print(f"  Create one with: cp mariadb_backup.conf.example mariadb_backup.conf")
        all_tests_passed = False
    
    # Test 5: MySQL connection
    if config_found and config_file:
        print_header("Test 5: MySQL Connection")
        if not test_mysql_connection(config_file):
            all_tests_passed = False
            print("\n  Troubleshooting tips:")
            print("  - Verify MySQL is running: systemctl status mariadb")
            print("  - Check credentials in config file")
            print("  - Test manually: mysql -u root -p")
    
    # Test 6: Backup directories
    print_header("Test 6: Backup Directories")
    if config_found and config_file:
        try:
            config = configparser.ConfigParser()
            config.read(config_file)
            
            backup_paths = []
            for backup_type in ['hourly', 'daily', 'monthly']:
                path = config['backup_paths'].get(backup_type)
                if path:
                    backup_paths.append(path)
                    if os.path.exists(path):
                        if os.access(path, os.W_OK):
                            print_success(f"{backup_type} directory exists and writable: {path}")
                        else:
                            print_error(f"{backup_type} directory not writable: {path}")
                            all_tests_passed = False
                    else:
                        print_warning(f"{backup_type} directory does not exist: {path}")
                        print(f"  Create with: mkdir -p {path}")
            
            # Test 7: Disk space
            if backup_paths:
                print_header("Test 7: Disk Space")
                check_disk_space(backup_paths)
                
        except Exception as e:
            print_error(f"Error checking backup directories: {e}")
    
    # Test 8: Test backup (optional)
    print_header("Test 8: Test Backup (Optional)")
    print("To test creating a backup, run:")
    print(f"  {manager_script} --backup manual --path /tmp/test_backup")
    
    # Summary
    print_header("Summary")
    if all_tests_passed:
        print_success("All critical tests passed!")
        print("\nNext steps:")
        print("  1. Run interactive menu: ./mariadb_manager.py")
        print("  2. Create test backup: ./mariadb_manager.py --backup manual")
        print("  3. Setup cron jobs (see README.md)")
        print("\nFor help: ./mariadb_manager.py --help")
    else:
        print_error("Some tests failed. Please fix the issues above before continuing.")
        print("\nFor installation help, see README.md")
        return 1
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
