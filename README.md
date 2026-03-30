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

- **`machine_setup_monitor.py`** — Background daemon that watches `machines.yaml` for new entries and automatically triggers setup.
- **`notes_monitor.py`** — Monitors a macOS Notes entry in real-time (reads the Notes SQLite DB). Handy for tracking dynamically updated IPs or notes.
- **`restore_backup.sh`** — Interactive script to restore `users.yaml.bak` backups on remote machines.

#### Requirements

- Python 3
- `sshpass` (for password-based SSH auth): `brew install sshpass`
- SSH access to your bastion/jump host

---

### dbfetch — DB Credentials Fetcher

SSHes into remote staging servers, reads `config/database.yml`, extracts DB credentials, and saves them locally.

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

### sqlrun — SQL Query Tool

Run tsql queries against any staging DB using saved credentials. Select a server once, query freely — no credentials ever typed.

**Use case:** You have 20+ staging SQL Server DBs. `sqlrun` manages SSH tunnels and credentials behind the scenes — you just write SQL.

#### Commands

```bash
sqlrun use <name>                    # Set active server (persists across sessions)
sqlrun status                        # Show active server info
sqlrun list                          # List all servers and their status
sqlrun query "<SQL>"                 # Run query against active server
sqlrun query --db <name> "<SQL>"     # One-off query without changing active server
sqlrun query -f <file.sql>           # Run SQL from a file
sqlrun shell                         # Open interactive SQL shell
```

#### Output formats

```bash
sqlrun query --format table "<SQL>"  # Aligned columns (default)
sqlrun query --format tsv "<SQL>"    # Tab-separated (for agents/scripts)
sqlrun query --format json "<SQL>"   # JSON array
sqlrun query --no-headers "<SQL>"    # Omit column headers
```

#### Example workflow

```bash
# Pick your DB
sqlrun use tallgrass-project

# Query freely
sqlrun query "SELECT TOP 10 * FROM users"

# Pipe SQL in
echo "SELECT @@VERSION" | sqlrun query

# One-off on a different DB without changing active
sqlrun query --db targa-project "SELECT COUNT(*) FROM jobs"

# Interactive shell
sqlrun shell
```

#### How it works

1. Reads credentials from `databases.yaml` (populated by `dbfetch`)
2. Opens an SSH tunnel through the bastion to the SQL Server
3. Runs `tsql` locally against the tunnel
4. Tears down the tunnel on exit

#### Requirements

- `tsql` (freetds): `brew install freetds`
- Credentials fetched via `dbfetch fetch --all`

---

*More tools coming soon.*
