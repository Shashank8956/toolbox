#!/usr/bin/env python3
"""
Machine Setup Automation Script
Monitors a YAML config file for new machine entries and automatically:
1. Copies SSH keys to the remote machine
2. SSHs into the machine
3. Edits users.yaml with predefined values
4. Runs appusers command
5. Reports success/failure
"""

import yaml
import time
import subprocess
import os
import tempfile
from pathlib import Path
from datetime import datetime
import hashlib


class MachineSetupMonitor:
    def __init__(self, config_file="machines.yaml", log_file="setup.log"):
        self.config_file = Path(config_file)
        self.log_file = Path(log_file)
        self.processed_machines = self._load_processed_machines()
        self.last_file_hash = None
        
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
    
    def _load_processed_machines(self):
        """Load the list of already processed machines from a tracking file."""
        tracking_file = Path(".processed_machines")
        if tracking_file.exists():
            with open(tracking_file, 'r') as f:
                return set(line.strip() for line in f if line.strip())
        return set()
    
    def _save_processed_machine(self, machine_id):
        """Save a machine ID as processed."""
        tracking_file = Path(".processed_machines")
        with open(tracking_file, 'a') as f:
            f.write(f"{machine_id}\n")
        self.processed_machines.add(machine_id)
    
    def _get_machine_id(self, machine):
        """Generate a unique ID for a machine."""
        return f"{machine['name']}_{machine['ip']}"
    
    def _get_file_hash(self):
        """Get hash of config file to detect changes."""
        with open(self.config_file, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def log(self, message, level="INFO"):
        """Log a message to both console and log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        print(log_message)
        
        with open(self.log_file, 'a') as f:
            f.write(log_message + "\n")
    
    def load_config(self):
        """Load and parse the YAML config file."""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('machines', [])
        except Exception as e:
            self.log(f"Error loading config: {e}", "ERROR")
            return []
    
    def run_command(self, command, stdin_input=None, timeout=30):
        """Run a shell command and return output."""
        try:
            self.log(f"Running command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=stdin_input
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.log(f"Command timed out: {command}", "ERROR")
            return -1, "", "Command timed out"
        except Exception as e:
            self.log(f"Error running command: {e}", "ERROR")
            return -1, "", str(e)
    
    def copy_ssh_key(self, machine):
        """Copy SSH key to remote machine via ProxyJump."""
        user = machine.get('user', 'wti')
        ip = machine['ip']
        jump_host = machine['jump_host']
        ssh_key = machine.get('ssh_key', '~/.ssh/id_ed25519.pub')
        ssh_key = os.path.expanduser(ssh_key)
        ssh_password = machine.get('ssh_password', '')
        
        # Check if key exists
        if not Path(ssh_key).exists():
            self.log(f"SSH key not found: {ssh_key}", "ERROR")
            return False
        
        # Build command with sshpass if password is provided
        if ssh_password:
            command = f"sshpass -p '{ssh_password}' ssh-copy-id -i {ssh_key} -o ProxyJump={user}@{jump_host} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {user}@{ip}"
        else:
            command = f"ssh-copy-id -i {ssh_key} -o ProxyJump={user}@{jump_host} -o StrictHostKeyChecking=no {user}@{ip}"
        
        print(f"\n📋 Step 1/4: Copying SSH key to {machine['name']} ({ip})...")
        self.log(f"Copying SSH key to {machine['name']} ({ip})...")
        
        returncode, stdout, stderr = self.run_command(command, timeout=60)
        
        if returncode == 0:
            print(f"✅ SSH key copied successfully - Passwordless SSH enabled!")
            self.log(f"✓ SSH key copied successfully to {machine['name']}", "SUCCESS")
            return True
        else:
            print(f"❌ Failed to copy SSH key")
            self.log(f"✗ Failed to copy SSH key: {stderr}", "ERROR")
            return False
    
    def create_users_yaml_content(self, config):
        """Create the users.yaml content from config."""
        # Convert the config dict to YAML format
        return yaml.dump(config, default_flow_style=False, sort_keys=False)
    
    def setup_machine(self, machine):
        """Execute the full setup process on a machine."""
        user = machine.get('user', 'wti')
        ip = machine['ip']
        jump_host = machine['jump_host']
        name = machine['name']
        
        self.log(f"\n{'='*60}")
        self.log(f"Starting setup for machine: {name} ({ip})")
        self.log(f"{'='*60}")
        
        # Step 1: Copy SSH key
        if not self.copy_ssh_key(machine):
            self.log(f"Setup failed for {name}: Could not copy SSH key", "ERROR")
            return False
        
        # Step 2-8: SSH in and configure
        print(f"\n📋 Step 2/4: Connecting to {name} via SSH...")
        self.log(f"Connecting to {name} via SSH...")
        
        # Create the users.yaml content
        users_yaml_content = ""
        if 'users_yaml_config' in machine:
            users_yaml_content = self.create_users_yaml_content(machine['users_yaml_config'])
            self.log(f"Users YAML content:\n{users_yaml_content}")
        
        # Create a script to run on the remote machine
        remote_script = f"""
set -e
source ~/.bashrc 2>/dev/null || source ~/.bash_profile 2>/dev/null || true
echo "STEP:SSH_CONNECTED"
cd /srv/www/apps/revenue_accounting || {{ echo "STEP:CD_FAILED"; exit 1; }}
echo "STEP:CD_SUCCESS"
if [ ! -f users.yaml ]; then
    echo "STEP:YAML_NOT_FOUND"
    exit 1
fi
cp users.yaml users.yaml.bak
# Check if user already exists in the YAML
if grep -q "^ssingh:" users.yaml; then
    echo "STEP:YAML_ALREADY_EXISTS"
    echo "User ssingh already exists in users.yaml, skipping duplicate entry"
else
    # User doesn't exist, append it with a blank line separator
    echo "STEP:YAML_ADDING_USER"
    echo "" >> users.yaml
    cat >> users.yaml << 'EOFYAML'
{users_yaml_content}
EOFYAML
fi
echo "STEP:YAML_UPDATED"
appusers_output=$(RAILS_ENV=production bundle exec rake dev:add_users 2>&1)
echo "$appusers_output"
# Extract only lines mentioning ssingh for user review
ssingh_lines=$(echo "$appusers_output" | grep -i "ssingh")
echo "SSINGH_OUTPUT:$ssingh_lines"
# Check for specific success message for user ssingh
if echo "$appusers_output" | grep -q "User 'ssingh' created successfully"; then
    echo "STEP:APPUSERS_SUCCESS"
    echo "STEP:SHOWING_YAML_CONTENT"
    echo "=== users.yaml content after update ==="
    cat users.yaml
    echo "=== end of users.yaml ==="
elif echo "$appusers_output" | grep -q "User 'ssingh' not created => Validation failed: Login has already been taken"; then
    echo "STEP:APPUSERS_EXISTS"
    echo "STEP:SHOWING_YAML_CONTENT"
    echo "=== users.yaml content after update ==="
    cat users.yaml
    echo "=== end of users.yaml ==="
elif echo "$appusers_output" | grep -qi "ssingh"; then
    echo "STEP:APPUSERS_PARTIAL"
    echo "SSINGH_MESSAGE:$appusers_output"
else
    echo "STEP:APPUSERS_FAIL"
    echo "ERROR_MESSAGE:$appusers_output"
fi
echo "STEP:LOGOUT"
"""
        
        # Save script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(remote_script)
            script_file = f.name
        
        try:
            # SSH command with ProxyJump using login shell to load aliases
            ssh_command = f"ssh -o ProxyJump={user}@{jump_host} {user}@{ip} 'bash -l -s' < {script_file}"
            
            returncode, stdout, stderr = self.run_command(ssh_command, timeout=120)
            
            self.log(f"Remote execution output:\n{stdout}")
            if stderr:
                self.log(f"Remote execution errors:\n{stderr}", "WARNING")
            
            # Parse output for terminal display
            if "STEP:SSH_CONNECTED" in stdout:
                print(f"✅ Successfully connected via SSH")
            else:
                print(f"❌ Failed to establish SSH connection")
                return False
            
            print(f"\n📋 Step 3/4: Updating users.yaml...")
            if "STEP:CD_SUCCESS" in stdout:
                print(f"✅ Successfully navigated to rails directory")
            elif "STEP:CD_FAILED" in stdout:
                print(f"❌ Failed to navigate to rails directory")
                return False
            
            if "STEP:YAML_ALREADY_EXISTS" in stdout:
                print(f"ℹ️  User 'ssingh' already exists in users.yaml, skipping duplicate entry")
            elif "STEP:YAML_ADDING_USER" in stdout:
                print(f"➕ Adding user 'ssingh' to users.yaml")
            
            if "STEP:YAML_UPDATED" in stdout:
                print(f"✅ users.yaml processed successfully")
            elif "STEP:YAML_NOT_FOUND" in stdout:
                print(f"❌ users.yaml file not found")
                return False
            
            print(f"\n📋 Step 4/4: Running appusers command...")
            
            # Extract and show only ssingh-related output
            ssingh_output = []
            for line in stdout.split('\n'):
                if 'SSINGH_OUTPUT:' in line:
                    ssingh_info = line.split('SSINGH_OUTPUT:', 1)[1]
                    if ssingh_info.strip():
                        ssingh_output.append(ssingh_info)
            
            if ssingh_output:
                print(f"\n{'='*60}")
                print(f"📄 Output for user 'ssingh':")
                print(f"{'='*60}")
                for line in ssingh_output:
                    print(f"  {line}")
                print(f"{'='*60}\n")
            
            if "STEP:APPUSERS_SUCCESS" in stdout:
                print(f"✅ User 'ssingh' created successfully!")
                
                # Show the users.yaml content
                if "STEP:SHOWING_YAML_CONTENT" in stdout:
                    print(f"\n📄 Contents of users.yaml after update:")
                    print(f"{'='*60}")
                    in_yaml = False
                    for line in stdout.split('\n'):
                        if '=== users.yaml content after update ===' in line:
                            in_yaml = True
                            continue
                        elif '=== end of users.yaml ===' in line:
                            in_yaml = False
                            continue
                        if in_yaml:
                            print(f"  {line}")
                    print(f"{'='*60}")
                    
            elif "STEP:APPUSERS_EXISTS" in stdout:
                print(f"✅ User 'ssingh' already exists (no action needed)")
                
                # Show the users.yaml content
                if "STEP:SHOWING_YAML_CONTENT" in stdout:
                    print(f"\n📄 Contents of users.yaml after update:")
                    print(f"{'='*60}")
                    in_yaml = False
                    for line in stdout.split('\n'):
                        if '=== users.yaml content after update ===' in line:
                            in_yaml = True
                            continue
                        elif '=== end of users.yaml ===' in line:
                            in_yaml = False
                            continue
                        if in_yaml:
                            print(f"  {line}")
                    print(f"{'='*60}")
                    
            elif "STEP:APPUSERS_PARTIAL" in stdout:
                print(f"⚠️  User 'ssingh' mentioned in output but not confirmed as created")
                # Extract the ssingh message
                for line in stdout.split('\n'):
                    if 'SSINGH_MESSAGE:' in line:
                        msg = line.split('SSINGH_MESSAGE:', 1)[1]
                        print(f"   Output about ssingh: {msg}")
                        self.log(f"Partial success for ssingh: {msg}", "WARNING")
            elif "STEP:APPUSERS_FAIL" in stdout:
                print(f"❌ Failed to create user 'ssingh'")
                # Extract the error message
                for line in stdout.split('\n'):
                    if 'ERROR_MESSAGE:' in line:
                        msg = line.split('ERROR_MESSAGE:', 1)[1]
                        print(f"   Error: {msg}")
                        self.log(f"Failed to create ssingh: {msg}", "ERROR")
            else:
                print(f"⚠️  appusers command completed (check logs for details)")
            
            if "STEP:LOGOUT" in stdout:
                print(f"✅ Logged out successfully")
            
            # Check for success/failure - succeed if user was created OR already exists
            if "STEP:APPUSERS_SUCCESS" in stdout or "STEP:APPUSERS_EXISTS" in stdout:
                print(f"\n{'='*60}")
                print(f"✅✅✅ SUCCESS: Machine {name} configured successfully!")
                print(f"{'='*60}\n")
                self.log(f"✓✓✓ SUCCESS: Machine {name} configured successfully!", "SUCCESS")
                return True
            elif "STEP:CD_FAILED" in stdout or "STEP:YAML_NOT_FOUND" in stdout or "STEP:APPUSERS_PARTIAL" in stdout or "STEP:APPUSERS_FAIL" in stdout:
                print(f"\n{'='*60}")
                print(f"❌❌❌ FAIL: Machine {name} configuration failed")
                print(f"{'='*60}\n")
                self.log(f"✗✗✗ FAIL: Machine {name} configuration failed", "ERROR")
                return False
            else:
                print(f"\n{'='*60}")
                print(f"⚠️  UNKNOWN: Machine {name} status unclear - check logs")
                print(f"{'='*60}\n")
                self.log(f"? UNKNOWN: Machine {name} status unclear", "WARNING")
                return False
                
        finally:
            # Clean up temp file
            try:
                os.unlink(script_file)
            except:
                pass
    
    def process_new_machines(self):
        """Process any new machines in the config."""
        machines = self.load_config()
        new_machines_found = False
        
        for machine in machines:
            # Skip if disabled
            if not machine.get('enabled', True):
                continue
            
            # Check if already processed
            machine_id = self._get_machine_id(machine)
            if machine_id in self.processed_machines:
                continue
            
            # Validate required fields
            required_fields = ['name', 'ip', 'jump_host']
            if not all(field in machine for field in required_fields):
                self.log(f"Skipping invalid machine entry: {machine}", "WARNING")
                continue
            
            new_machines_found = True
            self.log(f"\n🔔 NEW MACHINE DETECTED: {machine['name']}")
            
            # Process the machine
            success = self.setup_machine(machine)
            
            if success:
                self._save_processed_machine(machine_id)
                self.log(f"✓ Machine {machine['name']} marked as processed")
            else:
                self.log(f"✗ Machine {machine['name']} setup failed, will retry next time", "ERROR")
        
        return new_machines_found
    
    def monitor(self, interval=5):
        """Monitor the config file for changes."""
        self.log("="*60)
        self.log("Machine Setup Monitor Started")
        self.log(f"Config file: {self.config_file.absolute()}")
        self.log(f"Log file: {self.log_file.absolute()}")
        self.log(f"Check interval: {interval} seconds")
        self.log("="*60)
        
        # Process any existing unprocessed machines on startup
        self.log("\nChecking for unprocessed machines...")
        self.process_new_machines()
        self.last_file_hash = self._get_file_hash()
        
        self.log(f"\nMonitoring for changes... (Press Ctrl+C to stop)\n")
        
        try:
            while True:
                time.sleep(interval)
                
                # Check if file has changed
                current_hash = self._get_file_hash()
                if current_hash != self.last_file_hash:
                    self.log("\n📝 Config file changed, checking for new machines...")
                    self.last_file_hash = current_hash
                    self.process_new_machines()
                
        except KeyboardInterrupt:
            self.log("\n\nMonitoring stopped by user.")
        except Exception as e:
            self.log(f"\n\nUnexpected error: {e}", "ERROR")
            import traceback
            traceback.print_exc()


def main():
    import sys
    
    config_file = "machines.yaml"
    
    # Allow specifying config file as argument
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    try:
        monitor = MachineSetupMonitor(config_file=config_file)
        monitor.monitor(interval=5)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print(f"\nPlease create a config file at: {config_file}")
        print("See machines.yaml for the expected format.")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
