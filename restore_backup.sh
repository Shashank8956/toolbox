#!/bin/bash
# Script to restore users.yaml from backup on remote machines

JUMP_HOST="wti@213.165.235.206"
RAILS_DIR="/srv/www/apps/revenue_accounting"

# List of machines (add more as needed)
declare -A MACHINES=(
    ["tallgrass-project"]="172.100.11.102"
    ["support9"]="172.100.11.161"
)

for name in "${!MACHINES[@]}"; do
    ip="${MACHINES[$name]}"
    echo "========================================"
    echo "Checking $name ($ip)..."
    echo "========================================"
    
    # Check if backup exists
    ssh -o ProxyJump=$JUMP_HOST wti@$ip "cd $RAILS_DIR && ls -lh users.yaml* 2>/dev/null" || {
        echo "Could not access $name"
        continue
    }
    
    echo ""
    read -p "Restore backup on $name? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ssh -o ProxyJump=$JUMP_HOST wti@$ip "cd $RAILS_DIR && cp users.yaml.bak users.yaml && echo 'Restored!'" && {
            echo "✅ Backup restored on $name"
        } || {
            echo "❌ Failed to restore on $name"
        }
    else
        echo "Skipped $name"
    fi
    echo ""
done

echo "Done!"
