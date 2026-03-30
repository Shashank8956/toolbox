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

### dbfetch — DB Credentials Fetcher

SSHes into remote staging servers, reads `config/database.yml`, extracts DB credentials, and saves them locally for use with `tsql` or any SQL client.

**Use case:** You have multiple staging servers each with their own database. Instead of manually SSHing into each box to look up creds, `dbfetch` does it for you and stores everything in one place.

#### Commands

```bash
dbfetch add <name> <ip> [rails_dir]   # Register a staging server
dbfetch fetch <name>                  # SSH in, read database.yml, save creds
dbfetch fetch --all                   # Fetch creds from all servers at once
dbfetch list                          # List servers and fetch status
dbfetch show <name>                   # Display saved creds for a server
dbfetch logs                          # Show recent logs
```

#### How it works

When you run `dbfetch fetch <name>`:
1. SSHes into the server through the configured jump host
2. Navigates to the Rails app directory
3. Reads `config/database.yml`
4. Extracts credentials from the `production` (or `staging`/`development`) block
5. Saves them to `databases.yaml` locally

#### Configuration

Copy `databases.yaml.example` to `databases.yaml` and fill in your values:

```yaml
jump_host:
  user: "your_user"
  ip: "your.bastion.ip"

servers:
  my-staging-server:
    ip: "172.100.x.x"
    user: "wti"
    rails_directory: "/srv/www/apps/revenue_accounting"
```

> `databases.yaml` is gitignored — it will contain real credentials.

---

*More tools coming soon.*
