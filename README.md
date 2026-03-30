# toolbox

A growing collection of personal productivity and infrastructure automation tools.

## Tools

### rsh — Remote Setup Helper

A CLI tool to automate SSH setup and user provisioning on remote machines through a jump/bastion host.

**Use case:** You manage multiple remote servers behind a bastion. When a new machine is spun up, `rsh` handles copying SSH keys, updating user configs, and running provisioning commands — all automated.

#### Commands

```bash
rsh add <name> <ip>     # Add a machine and run setup automatically
rsh list                # List all machines and their setup status
rsh setup <name>        # Re-trigger setup for a machine
rsh ssh <name>          # SSH into a configured machine
rsh logs                # Show recent operation logs
```

#### How setup works

When you run `rsh add`:
1. Saves the machine to `machines.yaml`
2. Copies your SSH public key via `ssh-copy-id` through the jump host
3. SSHs into the machine and navigates to the configured directory
4. Backs up and merges user data into the target YAML file
5. Runs the configured post-provisioning command
6. Marks the machine as setup-complete (won't re-run unless forced)

#### Configuration

Copy `machines.yaml.example` to `machines.yaml` and fill in your values:

```yaml
jump_host:
  user: "your_user"
  ip: "your.bastion.ip"

setup_config:
  ssh_key: "~/.ssh/id_ed25519.pub"
  ssh_password: "optional_password"
  rails_directory: "/path/to/app"
  yaml_file: "users.yaml"
  yaml_updates:
    newuser:
      password: 'SecurePass'
      admin: true
      email: user@example.com
  post_edit_command: "your_provisioning_command"
```

#### Related tools

- **`machine_setup_monitor.py`** — Background daemon that watches `machines.yaml` for new entries and automatically triggers setup. Useful when machines are added by other scripts or teammates.
- **`notes_monitor.py`** — Monitors a macOS Notes entry in real-time (reads the Notes SQLite DB). Handy for tracking dynamically updated IPs or notes.
- **`restore_backup.sh`** — Interactive script to restore `users.yaml.bak` backups on remote machines.

#### Requirements

- Python 3
- `sshpass` (for password-based SSH auth): `brew install sshpass`
- SSH access to your bastion/jump host

---

*More tools coming soon.*
