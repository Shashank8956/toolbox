#!/usr/bin/env python3
"""
Remote Setup Helper (rsh)
CLI tool to manage remote machines and automate SSH setup
"""

import sys
import yaml
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime
from threading import Thread
import fcntl
import logging

# Resolve symlink to get the actual script location
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "machines.yaml"
LOG_FILE = SCRIPT_DIR / "rsh.log"
LOCK_FILE = SCRIPT_DIR / ".rsh.lock"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, config_file):
        self.config_file = Path(config_file)
        
    def load(self):
        """Load configuration from YAML file."""
        if not self.config_file.exists():
            logger.error(f"Config file not found: {self.config_file}")
            sys.exit(1)
        
        with open(self.config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def save(self, config):
        """Save configuration to YAML file."""
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    def add_machine(self, name, ip, user="wti"):
        """Add a new machine to the config."""
        config = self.load()
        
        if 'machines' not in config:
            config['machines'] = {}
        
        # Check if IP already exists
        for machine_name, details in config['machines'].items():
            if details['ip'] == ip:
                logger.warning(f"Machine with IP {ip} already exists as '{machine_name}'")
                return False, machine_name
        
        # Add new machine
        config['machines'][name] = {
            'ip': ip,
            'user': user,
            'setup_completed': False,
            'last_setup_time': None
        }
        
        self.save(config)
        logger.info(f"Added machine: {name} ({ip})")
        return True, name
    
    def get_machine(self, name):
        """Get machine details by name."""
        config = self.load()
        return config.get('machines', {}).get(name)
    
    def list_machines(self):
        """List all machines."""
        config = self.load()
        return config.get('machines', {})
    
    def mark_setup_completed(self, name):
        """Mark machine setup as completed."""
        config = self.load()
        if name in config.get('machines', {}):
            config['machines'][name]['setup_completed'] = True
            config['machines'][name]['last_setup_time'] = datetime.now().isoformat()
            self.save(config)
            logger.info(f"Marked {name} as setup completed")


def add_ssh_config_entry(name, ip, user="wti", proxy_jump="wti@213.165.235.206"):
    """Add an SSH config entry to ~/.ssh/config under the correct section.
    
    Support machines (name starts with 'support') go under '# Support Boxes'.
    All other machines go under '# Project Boxes'.
    Skips if Host entry already exists.
    """
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    
    if not os.path.exists(ssh_config_path):
        logger.warning(f"SSH config file not found: {ssh_config_path}")
        return False
    
    with open(ssh_config_path, 'r') as f:
        content = f.read()
    
    # Check if entry already exists
    if f"Host {name}" in content:
        print(f"ℹ️  SSH config entry for '{name}' already exists, skipping")
        logger.info(f"SSH config entry for '{name}' already exists")
        return True
    
    # Build the new entry
    new_entry = f"\nHost {name}\n    HostName {ip}\n    User {user}\n    ProxyJump {proxy_jump}\n"
    
    # Determine the correct section
    is_support = name.lower().startswith("support")
    
    lines = content.split('\n')
    insert_index = None
    
    if is_support:
        # Find '# Support Boxes' section and insert at the end of it
        # Walk from the end of the section backwards to find the last Host block
        support_start = None
        next_section = None
        for i, line in enumerate(lines):
            if line.strip() == '# Support Boxes':
                support_start = i
            elif support_start is not None and line.strip().startswith('#') and not line.strip().startswith('# Support'):
                # Found the next section comment after Support Boxes
                next_section = i
                break
        
        if support_start is not None:
            if next_section is not None:
                # Insert before the next section (with a blank line before the section comment)
                insert_index = next_section
            else:
                # Support Boxes is the last section, find end of last Host block
                # Walk backwards from end to find last non-empty line in the section
                for i in range(len(lines) - 1, support_start, -1):
                    if lines[i].strip():
                        insert_index = i + 1
                        break
                if insert_index is None:
                    insert_index = support_start + 1
    else:
        # Find '# Project Boxes' section, insert before '# Support Boxes'
        support_start = None
        for i, line in enumerate(lines):
            if line.strip() == '# Support Boxes':
                support_start = i
                break
        
        if support_start is not None:
            # Insert before '# Support Boxes' line
            insert_index = support_start
        else:
            # No Support Boxes section, find end of Project Boxes section
            project_start = None
            for i, line in enumerate(lines):
                if line.strip() == '# Project Boxes':
                    project_start = i
                    break
            if project_start is not None:
                # Find the next section comment after Project Boxes
                for i in range(project_start + 1, len(lines)):
                    if lines[i].strip().startswith('#') and not lines[i].strip().startswith('# Project'):
                        insert_index = i
                        break
                if insert_index is None:
                    insert_index = len(lines)
    
    if insert_index is None:
        logger.warning("Could not find the right section in SSH config, appending at end")
        insert_index = len(lines)
    
    # Insert the new entry
    lines.insert(insert_index, new_entry)
    
    with open(ssh_config_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ Added SSH config entry for '{name}' under {'# Support Boxes' if is_support else '# Project Boxes'}")
    logger.info(f"Added SSH config entry: Host {name} -> {ip}")
    return True


class MachineSetup:
    def __init__(self, config_manager):
        self.cm = config_manager
        self.config = self.cm.load()
    
    def setup_machine(self, machine_name):
        """Run the complete setup process for a machine."""
        machine = self.cm.get_machine(machine_name)
        if not machine:
            logger.error(f"Machine {machine_name} not found")
            return False
        
        if machine.get('setup_completed'):
            logger.info(f"Machine {machine_name} already setup. Skipping.")
            return True
        
        logger.info(f"Starting setup for {machine_name} ({machine['ip']})")
        
        jump_host = self.config['jump_host']
        setup_config = self.config['setup_config']
        
        # Step 1: Copy SSH key
        if not self._copy_ssh_key(machine, jump_host, setup_config):
            return False
        
        # Step 2-9: SSH and configure
        if not self._configure_machine(machine, jump_host, setup_config):
            return False
        
        # Mark as completed
        self.cm.mark_setup_completed(machine_name)
        logger.info(f"✅ Setup completed successfully for {machine_name}")
        return True
    
    def _copy_ssh_key(self, machine, jump_host, setup_config):
        """Copy SSH key to remote machine."""
        print(f"\n📋 Step 1/4: Copying SSH key to {machine['ip']}...")
        logger.info(f"Step 1: Copying SSH key to {machine['ip']}")
        
        ssh_key = os.path.expanduser(setup_config['ssh_key'])
        ssh_password = setup_config.get('ssh_password', '')
        proxy_jump = f"{jump_host['user']}@{jump_host['ip']}"
        target = f"{machine['user']}@{machine['ip']}"
        
        # Build the command with sshpass if password is provided
        if ssh_password:
            cmd = [
                'sshpass', '-p', ssh_password,
                'ssh-copy-id',
                '-i', ssh_key,
                '-o', f'ProxyJump={proxy_jump}',
                '-o', 'StrictHostKeyChecking=no',  # Auto-accept fingerprint
                '-o', 'UserKnownHostsFile=/dev/null',  # Don't save to known_hosts during copy
                target
            ]
        else:
            cmd = [
                'ssh-copy-id',
                '-i', ssh_key,
                '-o', f'ProxyJump={proxy_jump}',
                '-o', 'StrictHostKeyChecking=no',  # Auto-accept fingerprint
                target
            ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                print(f"✅ SSH key copied successfully - Passwordless SSH enabled!")
                logger.info("SSH key copied successfully")
                logger.info(f"Output: {result.stdout}")
                return True
            else:
                print(f"❌ Failed to copy SSH key")
                logger.error(f"Failed to copy SSH key: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"❌ SSH key copy timed out")
            logger.error("SSH key copy timed out")
            return False
        except Exception as e:
            print(f"❌ Error copying SSH key: {e}")
            logger.error(f"Error copying SSH key: {e}")
            return False
    
    def _configure_machine(self, machine, jump_host, setup_config):
        """SSH into machine and run configuration commands."""
        print(f"\n📋 Step 2/4: Connecting to {machine['ip']} via SSH...")
        logger.info(f"Step 2-4: Configuring machine {machine['ip']}")
        
        proxy_jump = f"{jump_host['user']}@{jump_host['ip']}"
        target = f"{machine['user']}@{machine['ip']}"
        
        # Get configuration
        rails_dir = setup_config.get('rails_directory', '/srv/www/apps/revenue_accounting')
        yaml_file = setup_config.get('yaml_file', 'users.yaml')
        yaml_updates = setup_config.get('yaml_updates', {})
        post_cmd = setup_config.get('post_edit_command', 'appusers')
        
        # Convert yaml_updates to YAML format with proper quoting
        import io
        yaml_stream = io.StringIO()
        yaml.dump(yaml_updates, yaml_stream, default_flow_style=False, sort_keys=False, default_style="'")
        yaml_content = yaml_stream.getvalue()
        
        # Create the command to run remotely
        remote_commands = f"""
source ~/.bashrc 2>/dev/null || source ~/.bash_profile 2>/dev/null || true
echo "STEP:SSH_CONNECTED"
cd {rails_dir} || {{ echo "STEP:CD_FAILED"; exit 1; }}
echo "STEP:CD_SUCCESS"
if [ ! -f {yaml_file} ]; then
    echo "STEP:YAML_NOT_FOUND"
    exit 1
fi
cp {yaml_file} {yaml_file}.bak
# Check if user already exists in the YAML
if grep -q "^ssingh:" {yaml_file}; then
    echo "STEP:YAML_ALREADY_EXISTS"
    echo "User ssingh already exists in {yaml_file}, skipping duplicate entry"
else
    # User doesn't exist, append it with a blank line separator
    echo "STEP:YAML_ADDING_USER"
    echo "" >> {yaml_file}
    cat >> {yaml_file} << 'EOFYAML'
ssingh:
  password: '{yaml_updates['ssingh']['password']}'
  admin: {str(yaml_updates['ssingh']['admin']).lower()}
  email: {yaml_updates['ssingh']['email']}
EOFYAML
fi
echo "STEP:YAML_UPDATED"
appusers_output=$({post_cmd} 2>&1)
echo "$appusers_output"
# Extract only lines mentioning ssingh for user review
ssingh_lines=$(echo "$appusers_output" | grep -i "ssingh")
echo "SSINGH_OUTPUT:$ssingh_lines"
# Check for specific success message for user ssingh
if echo "$appusers_output" | grep -q "User 'ssingh' created successfully"; then
    echo "STEP:APPUSERS_SUCCESS"
    echo "STEP:SHOWING_YAML_CONTENT"
    echo "=== users.yaml content after update ==="
    cat {yaml_file}
    echo "=== end of users.yaml ==="
elif echo "$appusers_output" | grep -q "User 'ssingh' not created => Validation failed: Login has already been taken"; then
    echo "STEP:APPUSERS_EXISTS"
    echo "STEP:SHOWING_YAML_CONTENT"
    echo "=== users.yaml content after update ==="
    cat {yaml_file}
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
        
        cmd = [
            'ssh',
            '-o', f'ProxyJump={proxy_jump}',
            '-o', 'StrictHostKeyChecking=no',
            '-t',  # Force pseudo-terminal allocation
            target,
            f'bash -l <<\'EOFCOMMAND\'\n{remote_commands}\nEOFCOMMAND\n'
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            # Log full output to log file
            logger.info(f"Remote command output:\n{result.stdout}")
            if result.stderr:
                logger.warning(f"Remote command stderr:\n{result.stderr}")
            
            # Parse output for terminal display
            output = result.stdout
            
            if "STEP:SSH_CONNECTED" in output:
                print(f"✅ Successfully connected via SSH")
            else:
                print(f"❌ Failed to establish SSH connection")
                return False
            
            print(f"\n📋 Step 3/4: Updating users.yaml...")
            if "STEP:CD_SUCCESS" in output:
                print(f"✅ Successfully navigated to rails directory")
            elif "STEP:CD_FAILED" in output:
                print(f"❌ Failed to navigate to rails directory")
                return False
            
            if "STEP:YAML_ALREADY_EXISTS" in output:
                print(f"ℹ️  User 'ssingh' already exists in users.yaml, skipping duplicate entry")
            elif "STEP:YAML_ADDING_USER" in output:
                print(f"➕ Adding user 'ssingh' to users.yaml")
            
            if "STEP:YAML_UPDATED" in output:
                print(f"✅ users.yaml processed successfully")
            elif "STEP:YAML_NOT_FOUND" in output:
                print(f"❌ users.yaml file not found")
                return False
            
            print(f"\n📋 Step 4/4: Running appusers command...")
            
            # Extract and show only ssingh-related output
            ssingh_output = []
            for line in output.split('\n'):
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
            
            if "STEP:APPUSERS_SUCCESS" in output:
                print(f"✅ User 'ssingh' created successfully!")
                
                # Show the users.yaml content
                if "STEP:SHOWING_YAML_CONTENT" in output:
                    print(f"\n📄 Contents of users.yaml after update:")
                    print(f"{'='*60}")
                    in_yaml = False
                    for line in output.split('\n'):
                        if '=== users.yaml content after update ===' in line:
                            in_yaml = True
                            continue
                        elif '=== end of users.yaml ===' in line:
                            in_yaml = False
                            continue
                        if in_yaml:
                            print(f"  {line}")
                    print(f"{'='*60}")
                    
            elif "STEP:APPUSERS_EXISTS" in output:
                print(f"✅ User 'ssingh' already exists (no action needed)")
                
                # Show the users.yaml content
                if "STEP:SHOWING_YAML_CONTENT" in output:
                    print(f"\n📄 Contents of users.yaml after update:")
                    print(f"{'='*60}")
                    in_yaml = False
                    for line in output.split('\n'):
                        if '=== users.yaml content after update ===' in line:
                            in_yaml = True
                            continue
                        elif '=== end of users.yaml ===' in line:
                            in_yaml = False
                            continue
                        if in_yaml:
                            print(f"  {line}")
                    print(f"{'='*60}")
                    
            elif "STEP:APPUSERS_PARTIAL" in output:
                print(f"⚠️  User 'ssingh' mentioned in output but not confirmed as created")
                # Extract the ssingh message
                for line in output.split('\n'):
                    if 'SSINGH_MESSAGE:' in line:
                        msg = line.split('SSINGH_MESSAGE:', 1)[1]
                        print(f"   Output about ssingh: {msg}")
                        logger.warning(f"Partial success for ssingh: {msg}")
            elif "STEP:APPUSERS_FAIL" in output:
                print(f"❌ Failed to create user 'ssingh'")
                # Extract the error message
                for line in output.split('\n'):
                    if 'ERROR_MESSAGE:' in line:
                        msg = line.split('ERROR_MESSAGE:', 1)[1]
                        print(f"   Error: {msg}")
                        logger.error(f"Failed to create ssingh: {msg}")
            else:
                print(f"⚠️  appusers command completed (check logs for details)")
            
            if "STEP:LOGOUT" in output:
                print(f"✅ Logged out successfully")
            
            # Overall success check - succeed if user was created OR already exists
            if ("STEP:APPUSERS_SUCCESS" in output or "STEP:APPUSERS_EXISTS" in output) and result.returncode == 0:
                logger.info("✅ Configuration completed successfully")
                return True
            elif "STEP:APPUSERS_PARTIAL" in output or "STEP:APPUSERS_FAIL" in output:
                logger.error(f"❌ User creation failed or incomplete")
                print(f"❌ Setup incomplete - user 'ssingh' was not created successfully")
                return False
            else:
                logger.error(f"❌ Configuration failed with exit code {result.returncode}")
                print(f"❌ Configuration failed with exit code {result.returncode}")
                return False
                return False
                
        except subprocess.TimeoutExpired:
            print(f"❌ Remote configuration timed out")
            logger.error("Remote configuration timed out")
            return False
        except Exception as e:
            print(f"❌ Error during remote configuration: {e}")
            logger.error(f"Error during remote configuration: {e}")
            return False


def print_usage():
    """Print usage information."""
    print("""
Remote Setup Helper (rsh)

Usage:
  rsh add <name> <ip>           Add a new machine and run setup
  rsh list                      List all machines and their status
  rsh setup <name>              Manually trigger setup for a machine
  rsh ssh <name>                SSH into a machine by name
  rsh logs                      Show recent logs
  rsh help                      Show this help message

Examples:
  rsh add server1 192.168.1.100
  rsh list
  rsh setup server1
  rsh ssh server1
    """)


def cmd_add(args):
    """Add a new machine."""
    if len(args) < 2:
        print("Error: Missing arguments. Usage: rsh add <name> <ip>")
        return 1
    
    name = args[0]
    ip = args[1]
    
    cm = ConfigManager(CONFIG_FILE)
    added, existing_name = cm.add_machine(name, ip)
    
    if not added:
        print(f"Machine with IP {ip} already exists as '{existing_name}'")
        return 1
    
    print(f"✅ Added machine: {name} ({ip})")
    
    # Add SSH config entry to ~/.ssh/config
    config = cm.load()
    jump_host = config.get('jump_host', {})
    proxy_jump = f"{jump_host.get('user', 'wti')}@{jump_host.get('ip', '213.165.235.206')}"
    add_ssh_config_entry(name, ip, user="wti", proxy_jump=proxy_jump)
    
    # Start setup in background
    print(f"🔄 Starting setup for {name}...")
    print(f"📝 Check logs with: rsh logs")
    
    setup = MachineSetup(cm)
    success = setup.setup_machine(name)
    
    if success:
        print(f"✅ Setup completed successfully for {name}")
        return 0
    else:
        print(f"❌ Setup failed for {name}. Check logs for details.")
        return 1


def cmd_list(args):
    """List all machines."""
    cm = ConfigManager(CONFIG_FILE)
    machines = cm.list_machines()
    
    if not machines:
        print("No machines configured yet.")
        return 0
    
    print("\n" + "="*70)
    print(f"{'Name':<20} {'IP':<18} {'Status':<15} {'Last Setup'}")
    print("="*70)
    
    for name, details in machines.items():
        status = "✅ Completed" if details.get('setup_completed') else "⏳ Pending"
        last_setup = details.get('last_setup_time', 'Never')
        if last_setup and last_setup != 'Never':
            last_setup = last_setup.split('T')[0]  # Just show date
        
        print(f"{name:<20} {details['ip']:<18} {status:<15} {last_setup}")
    
    print("="*70 + "\n")
    return 0


def cmd_setup(args):
    """Manually trigger setup for a machine."""
    if len(args) < 1:
        print("Error: Missing machine name. Usage: rsh setup <name>")
        return 1
    
    name = args[0]
    cm = ConfigManager(CONFIG_FILE)
    
    if not cm.get_machine(name):
        print(f"Error: Machine '{name}' not found")
        return 1
    
    print(f"🔄 Starting setup for {name}...")
    setup = MachineSetup(cm)
    success = setup.setup_machine(name)
    
    if success:
        print(f"✅ Setup completed successfully for {name}")
        return 0
    else:
        print(f"❌ Setup failed for {name}")
        return 1


def cmd_ssh(args):
    """SSH into a machine by name."""
    if len(args) < 1:
        print("Error: Missing machine name. Usage: rsh ssh <name>")
        return 1
    
    name = args[0]
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    
    # Check if the host exists in ~/.ssh/config
    if os.path.exists(ssh_config_path):
        with open(ssh_config_path, 'r') as f:
            content = f.read()
        if f"Host {name}" not in content:
            print(f"❌ Host '{name}' not found in ~/.ssh/config")
            print(f"   Add it first with: rsh add {name} <ip>")
            return 1
    else:
        print(f"❌ SSH config file not found: {ssh_config_path}")
        return 1
    
    print(f"🔗 Connecting to {name}...")
    os.execvp("ssh", ["ssh", name])


def cmd_logs(args):
    """Show recent logs."""
    if not LOG_FILE.exists():
        print("No logs found yet.")
        return 0
    
    # Show last 50 lines
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            recent = lines[-50:]
            print(''.join(recent))
    except Exception as e:
        print(f"Error reading logs: {e}")
        return 1
    
    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_usage()
        return 1
    
    command = sys.argv[1].lower()
    args = sys.argv[2:]
    
    commands = {
        'add': cmd_add,
        'list': cmd_list,
        'setup': cmd_setup,
        'ssh': cmd_ssh,
        'logs': cmd_logs,
        'help': lambda x: (print_usage(), 0)[1],
    }
    
    if command not in commands:
        print(f"Unknown command: {command}")
        print_usage()
        return 1
    
    try:
        return commands[command](args)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
