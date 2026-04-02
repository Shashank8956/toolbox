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

Save a file locally → it instantly appears on the remote staging server. Run builds remotely with live output streamed back to your terminal. Manage branches and PRs across multiple repos in one command.

**Use case:** You have ~30 staging servers behind a bastion, each running the same polyglot monorepo (Ruby + Go). `rdev` removes all the friction: pick a server, edit code, build, tail logs, raise PRs — without ever manually SSHing in.

#### How it works

1. `rdev start` spawns a background daemon running `fswatch` on your local repo dirs
2. On every file save, `rsync` sends just that changed file to the active remote via ProxyJump
3. `rdev build` SSHes in with a login shell and streams build output line-by-line
4. `rdev check` does an rsync dry-run with checksum comparison to verify sync state

#### Setup

```bash
brew install fswatch          # file watcher (required)
cp config/rdev.yaml.example config/rdev.yaml
# Fill in jump_host, local_root, and any repo-specific build commands
```

#### Typical sprint workflow

```bash
# 1. Pick a server and start syncing
rdev start exxon-project

# 2. Create branches across all repos for your ticket
rdev branch WEMAIN-34066 25 dmt      # creates WEMAIN-34066--25x and WEMAIN-34066--dmt
                                      # locally + on remote if session is active

# 3. Edit code — files sync automatically on every save
rdev status                           # confirm daemon is alive + see last synced file
rdev check                            # verify remote matches local (byte-for-byte diff)
rdev check go-ra                      # scope to one repo

# 4. Build remotely and watch live output
rdev build go-ra
rdev build revenue_accounting         # runs assets + restart + wgod start

# 5. Watch app logs on the remote
rdev logs                             # tail all *.log in real-time (Ctrl+C to stop)
rdev logs production.log              # tail a specific file
rdev logs -n 100                      # last 100 lines, static (no follow)
rdev logs production.log -n 50

# 6. Manage the app server
rdev wgod status
rdev wgod restart

# 7. Run any one-off remote command
rdev exec "ps aux | grep puma"

# 8. When ready — commit, cherry-pick to sibling branches, push, raise all PRs
rdev raise-pr "WEMAIN-34066: Fix visit_status filter for function columns"
# → prints PR links for every branch at the end

# 9. Done
rdev stop
```

#### Command reference

**Session**

| Command | Description |
|---------|-------------|
| `rdev start <server> [repo ...]` | Start sync session. Spawns background daemon. Repos default to `config.default_repos`. |
| `rdev stop` | Kill daemon and clear session state. |
| `rdev status` | Show server, watched repos, daemon health, last synced file + timestamp. |
| `rdev list` | List all known servers and configured repos. |

**File sync**

| Command | Description |
|---------|-------------|
| *(automatic on save)* | Every file save triggers fswatch → rsync to remote. |
| `rdev check [repo]` | Dry-run diff — shows files that differ between local and remote. Nothing is transferred. |
| `rdev sync-logs [n]` | Show last n lines of the local daemon log (default 50). Includes sync errors and timestamps. |

**Build & server**

| Command | Description |
|---------|-------------|
| `rdev build [repo]` | Run the repo's configured build command on remote, stream output live. Defaults to first watched repo. |
| `rdev wgod [status\|start\|restart]` | Run wgod on the active remote server. Default: `status`. |
| `rdev exec "<cmd>"` | Run any command on the remote and stream output. |

**Logs**

| Command | Description |
|---------|-------------|
| `rdev logs` | Tail all `*.log` files on remote in real-time. |
| `rdev logs <file>` | Tail a specific log file. |
| `rdev logs -n <N>` | Show last N lines from all `*.log` (static, no follow). |
| `rdev logs <file> -n <N>` | Show last N lines from a specific file. |

**Git & branching**

| Command | Description |
|---------|-------------|
| `rdev branch <TICKET> <suffix...>` | Create `TICKET--<suffix>` branches across all `branch_repos`. Pulls after checkout. Mirrors on remote if session active. Use `--repos r1,r2` to override repos. |
| `rdev raise-pr "<message>"` | Commit current branch, cherry-pick new commits to all sibling `TICKET--*` branches, push all, open PRs via `gh`. Prints all PR links at the end. |
| `rdev git <git-args>` | Run a git command locally in `local_root`, then mirror it on remote watched repos. |

#### Branch suffixes

Suffixes in `rdev branch` resolve via `branch_targets` in `rdev.yaml`:

```
24   → origin/release/24.x.x.x.m
25   → origin/release/25.x.x.x.m
dmt  → origin/develop-mt
```

Unknown suffixes are appended to `origin/release/` automatically. Update `branch_targets` each sprint when the release branch changes.

#### Configuration

`config/rdev.yaml` (gitignored — copy from `.example`):

```yaml
jump_host:
  user: "wti"
  ip: "your.bastion.ip"

local_root: "/Users/you/code/wes/erp"   # parent of all repo dirs
remote_root: "/srv/www/apps"             # base path on remote servers

branch_repos:                            # repos to create branches in
  - revenue_accounting
  - go-ra

branch_targets:                          # suffix → origin branch (update each sprint)
  dmt: origin/develop-mt
  24: origin/release/24.2.18.1.m
  25: origin/release/25.1.6.2.m

default_repos:                           # repos watched when none specified in start
  - revenue_accounting
  - go-ra

repos:
  revenue_accounting:
    local_path: revenue_accounting
    remote_path: revenue_accounting
    log_dir: log                         # used by rdev logs
    build:
      cmd: "assets && touch tmp/restart.txt"
      post_cmd: "wgod start && wgod status"
  go-ra:
    local_path: go-ra
    remote_path: /home/wti/go*/src/ra    # glob resolved at session start
    build:
      cmd: "~/bin/build"
```

#### Requirements

- `fswatch`: `brew install fswatch`
- `gh` (GitHub CLI): `brew install gh` — needed for `raise-pr`
- SSH access through bastion (same setup as `rsh`)

---

*More tools coming soon.*
