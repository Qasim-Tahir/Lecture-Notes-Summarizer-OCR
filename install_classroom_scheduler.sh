#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unit_dir"
sed "s#__PROJECT_DIR__#${project_dir}#g" "$project_dir/classroom-batch.service.in" > "$unit_dir/classroom-batch.service"
cp "$project_dir/classroom-batch.timer.in" "$unit_dir/classroom-batch.timer"
systemctl --user daemon-reload
systemctl --user enable --now classroom-batch.timer
echo "Installed classroom-batch.timer. Check with: systemctl --user status classroom-batch.timer"
