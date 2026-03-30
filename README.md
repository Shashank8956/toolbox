# toolbox

A growing collection of personal productivity and infrastructure automation tools.

## Project Structure

```
toolbox/
├── bin/          # Executables — add this to PATH
│   ├── rsh
│   ├── dbfetch
│   ├── sqlrun
│   └── rdev
├── config/       # YAML configs (real configs gitignored, .example files committed)
│   ├── machines.yaml.example
│   ├── databases.yaml.example
│   └── rdev.yaml.example
├── logs/         # Runtime logs (gitignored)
├── archive/      # Old / one-time scripts kept for reference
└── README.md
```

**Setup:** Add `bin/` to your PATH in `~/.zshrc`:
```bash
export PATH="$PATH:/path/to/toolbox/bin"
```

---

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
1. Saves the machine to `config/machines.yaml`
2. Copies your SSH public key via `ssh-copy-id` through the jump host
3. SSHs into the machine and navigates to the configured directory
4. Backs up and merges user data into the target YAML file
5. Runs the configured post-provisioning command
6. Marks the machine as setup-complete (won't re-run unless forced)

#### Configuration

Copy `config/machines.yaml.example` to `config/machines.yaml` and fill in your values:

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

#### Requirements

- Python 3
- `sshpass` (for password-based SSH auth): `brew install sshpass`

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

Copy `config/databases.yaml.example` to `config/databases.yaml`:

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

> `config/databases.yaml` is gitignored — it will contain real credentials.

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
sqlrun use tallgrass-project
sqlrun query "SELECT TOP 10 * FROM users"
echo "SELECT @@VERSION" | sqlrun query
sqlrun query --db targa-project "SELECT COUNT(*) FROM jobs"
sqlrun shell
```

#### How it works

1. Reads credentials from `config/databases.yaml` (populated by `dbfetch`)
2. Opens an SSH tunnel through the bastion to the SQL Server
3. Runs `tsql` locally against the tunnel — tears down tunnel on exit

#### Requirements

- `tsql` (freetds): `brew install freetds`
- Credentials fetched first via `dbfetch fetch --all`

---

### rdev — Remote Dev Sync Tool

Watches local code files and instantly syncs changes to a remote staging server. Run builds remotely with live output. Feels like working locally.

**Use case:** You edit code in `/Users/you/code/wes/erp` locally. Every file save is instantly copied to the active remote server. Type `rdev build go-ra` and the remote build streams back to your terminal.

#### Commands

```bash
rdev start <server> [repo ...]   # Start sync session (default: revenue_accounting + go-ra)
rdev stop                        # Stop the sync daemon
rdev status                      # Show session info and daemon health
rdev build [repo]                # Run remote build, stream output live
rdev git <git-args>              # Run git cmd locally + mirror on remote repos
rdev exec <cmd>                  # Run any command on remote, stream output
rdev list                        # List servers and configured repos
rdev logs [n]                    # Show last n sync entries (default 50)
```

#### Example workflow

```bash
# Start watching tallgrass-project (syncs revenue_accounting + go-ra by default)
rdev start tallgrass-project

# Or watch a specific repo
rdev start tallgrass-project go-ra

# Save any file locally → it instantly appears on remote

# Run a build (streams live output)
rdev build go-ra
rdev build revenue_accounting    # runs assets + restart + wgod

# Switch branches everywhere at once
rdev git checkout main

# Run a one-off remote command
rdev exec "ps aux | grep wgod"

# Stop when done
rdev stop
```

#### How it works

1. `rdev start` spawns a background daemon that runs `fswatch` on your local repo dirs
2. On every file save, `rsync` sends just that file to the remote via SSH (ProxyJump bastion)
3. `rdev build` SSHes in with a pseudo-TTY and runs the repo's configured build command
4. Build output streams line-by-line to your terminal in real time

#### Configuration

Copy `config/rdev.yaml.example` to `config/rdev.yaml`:

```yaml
jump_host:
  user: "wti"
  ip: "your.bastion.ip"

local_root: "/Users/you/code/wes/erp"
remote_root: "/srv/www/apps"

default_repos:
  - revenue_accounting
  - go-ra

repos:
  revenue_accounting:
    local_path: revenue_accounting
    remote_path: revenue_accounting
    build:
      cmd: "assets && touch tmp/restart.txt"
      post_cmd: "wgod start && wgod status"
  go-ra:
    local_path: go-ra
    remote_path: go-ra
    build:
      cmd: "~/bin/build"
```

#### Requirements

- `fswatch`: `brew install fswatch`
- SSH access through bastion (same setup as `rsh`)

---

*More tools coming soon.*
