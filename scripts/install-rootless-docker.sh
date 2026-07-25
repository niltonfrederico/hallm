#!/usr/bin/env bash
# Install and configure a rootless Docker daemon dedicated to the hallm k3d cluster.
#
# Idempotent: every step checks current state before acting and prints
# [skip] / [ok] / [done]. Re-run safely after a partial failure.
#
# Run as your normal user. The script invokes sudo only for the system-level
# steps (package install, kernel module load, sysctl drop-in, systemd drop-in,
# group membership, storage chown).

set -euo pipefail

CONTEXT_NAME="${HALLM_DOCKER_CONTEXT:-hallm}"
STORAGE_MOUNT_PATH="${HALLM_STORAGE_MOUNT_PATH:-/mnt/hallm}"
SYSCTL_FILE="/etc/sysctl.d/90-hallm-rootless.conf"
BR_NETFILTER_MODULES_FILE="/etc/modules-load.d/br_netfilter.conf"
BR_NETFILTER_SYSCTL_FILE="/etc/sysctl.d/91-hallm-br-netfilter.conf"
CGROUP_DROPIN_DIR="/etc/systemd/system/user@.service.d"
CGROUP_DROPIN_FILE="${CGROUP_DROPIN_DIR}/delegate.conf"
USER_SOCK="unix:///run/user/$(id -u)/docker.sock"

step()  { printf '\n==> %s\n' "$*"; }
ok()    { printf '   [ok]   %s\n' "$*"; }
skip()  { printf '   [skip] %s\n' "$*"; }
done_() { printf '   [done] %s\n' "$*"; }
warn()  { printf '   [warn] %s\n' "$*" >&2; }

if [[ $EUID -eq 0 ]]; then
    echo "ERROR: run as your normal user, not root. The script uses sudo for the bits that need it." >&2
    exit 1
fi

# 1. Packages -----------------------------------------------------------------
step "1/9 Installing packages (docker, docker-rootless-extras, docker-buildx, slirp4netns, fuse-overlayfs, uidmap, dnsmasq)"
needed=()
for pkg in docker docker-rootless-extras docker-buildx slirp4netns fuse-overlayfs shadow dnsmasq; do
    if pacman -Qi "$pkg" >/dev/null 2>&1; then
        ok "$pkg already installed"
    else
        needed+=("$pkg")
    fi
done
if (( ${#needed[@]} > 0 )); then
    if command -v paru >/dev/null 2>&1; then
        paru -S --needed --noconfirm "${needed[@]}"
    elif command -v yay >/dev/null 2>&1; then
        yay -S --needed --noconfirm "${needed[@]}"
    else
        sudo pacman -S --needed --noconfirm "${needed[@]}"
    fi
    done_ "installed: ${needed[*]}"
fi

# subuid / subgid -------------------------------------------------------------
step "2/9 Verifying /etc/subuid and /etc/subgid entries"
if grep -q "^${USER}:" /etc/subuid && grep -q "^${USER}:" /etc/subgid; then
    ok "subuid/subgid already configured for $USER"
else
    sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$USER"
    done_ "added subuid/subgid range for $USER"
fi

# Rootless dockerd ------------------------------------------------------------
step "3/9 Installing rootless dockerd (user systemd service)"
if systemctl --user is-enabled docker >/dev/null 2>&1; then
    ok "user docker service already enabled"
elif command -v dockerd-rootless-setuptool.sh >/dev/null 2>&1; then
    dockerd-rootless-setuptool.sh install
    done_ "rootless dockerd installed via setup tool"
else
    # Arch Linux ships the user service unit directly; no setup tool needed.
    systemctl --user enable --now docker
    done_ "rootless dockerd enabled via systemd user service (Arch path)"
fi

if systemctl --user is-active docker >/dev/null 2>&1; then
    ok "user docker service active"
else
    systemctl --user enable --now docker
    done_ "started user docker service"
fi

if loginctl show-user "$USER" | grep -q '^Linger=yes$'; then
    ok "linger already enabled for $USER"
else
    sudo loginctl enable-linger "$USER"
    done_ "enabled linger for $USER (daemon survives logout)"
fi

# Privileged ports ------------------------------------------------------------
step "4/9 Allowing rootless to bind ports >=80 (sysctl)"
if [[ -f "$SYSCTL_FILE" ]] && grep -q '^net\.ipv4\.ip_unprivileged_port_start=80$' "$SYSCTL_FILE"; then
    ok "$SYSCTL_FILE already configured"
else
    echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee "$SYSCTL_FILE" >/dev/null
    sudo sysctl --system >/dev/null
    done_ "wrote $SYSCTL_FILE and reloaded sysctl"
fi

current_start=$(cat /proc/sys/net/ipv4/ip_unprivileged_port_start)
if (( current_start <= 80 )); then
    ok "ip_unprivileged_port_start=$current_start (active)"
else
    warn "ip_unprivileged_port_start=$current_start — sysctl may not have applied; reboot if k3d port binding fails"
fi

# br_netfilter ----------------------------------------------------------------
step "5/9 Loading br_netfilter so bridged ClusterIP traffic hits netfilter"
# k3d is single-node: pod->Service traffic is DNAT'd on the way in (routed L3),
# but the reply is bridged pod-to-pod on cni0. Without br_netfilter that reply
# skips conntrack and is never un-DNAT'd, so every ClusterIP (CoreDNS included)
# times out while pod-to-pod still works. The rootless daemon cannot load kernel
# modules itself, so load it here and persist it across reboots.
if lsmod | grep -qw br_netfilter; then
    ok "br_netfilter already loaded"
else
    sudo modprobe br_netfilter
    done_ "loaded br_netfilter"
fi

if [[ -f "$BR_NETFILTER_MODULES_FILE" ]] && grep -qx br_netfilter "$BR_NETFILTER_MODULES_FILE"; then
    ok "$BR_NETFILTER_MODULES_FILE already persists br_netfilter"
else
    echo br_netfilter | sudo tee "$BR_NETFILTER_MODULES_FILE" >/dev/null
    done_ "wrote $BR_NETFILTER_MODULES_FILE (loads br_netfilter on boot)"
fi

if [[ -f "$BR_NETFILTER_SYSCTL_FILE" ]] && grep -q '^net\.bridge\.bridge-nf-call-iptables=1$' "$BR_NETFILTER_SYSCTL_FILE"; then
    ok "$BR_NETFILTER_SYSCTL_FILE already configured"
else
    sudo tee "$BR_NETFILTER_SYSCTL_FILE" >/dev/null <<'EOF'
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
EOF
    sudo sysctl --system >/dev/null
    done_ "wrote $BR_NETFILTER_SYSCTL_FILE and reloaded sysctl"
fi

bridge_call=$(cat /proc/sys/net/bridge/bridge-nf-call-iptables 2>/dev/null || echo 0)
if [[ "$bridge_call" == "1" ]]; then
    ok "bridge-nf-call-iptables=1 (active)"
else
    warn "bridge-nf-call-iptables=$bridge_call — bridged ClusterIP NAT will fail; ensure br_netfilter is loaded"
fi

# cgroup v2 delegation --------------------------------------------------------
step "6/9 Delegating cpu/cpuset/io to the user systemd slice"
if [[ -f "$CGROUP_DROPIN_FILE" ]] && grep -q 'Delegate=cpu cpuset io memory pids' "$CGROUP_DROPIN_FILE"; then
    ok "$CGROUP_DROPIN_FILE already configured"
else
    sudo mkdir -p "$CGROUP_DROPIN_DIR"
    sudo tee "$CGROUP_DROPIN_FILE" >/dev/null <<'EOF'
[Service]
Delegate=cpu cpuset io memory pids
EOF
    sudo systemctl daemon-reload
    done_ "wrote $CGROUP_DROPIN_FILE — re-login required for it to take effect"
fi

controllers_file="/sys/fs/cgroup/user.slice/user-$(id -u).slice/cgroup.controllers"
if [[ -r "$controllers_file" ]]; then
    if grep -qw cpu "$controllers_file" && grep -qw cpuset "$controllers_file" && grep -qw io "$controllers_file"; then
        ok "cgroup delegation active in $controllers_file"
    else
        warn "cgroup controllers not yet delegated — re-login (or reboot) required"
    fi
fi

# GPU groups ------------------------------------------------------------------
step "7/9 Adding $USER to render and video groups (GPU passthrough)"
groups_to_add=()
for grp in render video; do
    if id -nG "$USER" | tr ' ' '\n' | grep -qx "$grp"; then
        ok "$USER already in $grp"
    else
        groups_to_add+=("$grp")
    fi
done
if (( ${#groups_to_add[@]} > 0 )); then
    sudo usermod -aG "$(IFS=,; echo "${groups_to_add[*]}")" "$USER"
    done_ "added to: ${groups_to_add[*]} — re-login required"
fi

# Storage mount ownership -----------------------------------------------------
step "8/9 Ensuring $STORAGE_MOUNT_PATH is owned by $USER"
if [[ ! -d "$STORAGE_MOUNT_PATH" ]]; then
    skip "$STORAGE_MOUNT_PATH does not exist yet — 'hallm cluster setup' will mount it (re-run this script after first setup)"
elif [[ "$(stat -c '%u' "$STORAGE_MOUNT_PATH")" == "$(id -u)" ]]; then
    ok "$STORAGE_MOUNT_PATH already owned by $USER"
else
    sudo chown -R "$USER:$USER" "$STORAGE_MOUNT_PATH"
    done_ "chowned $STORAGE_MOUNT_PATH to $USER"
fi

# Docker context --------------------------------------------------------------
step "9/9 Creating Docker context '$CONTEXT_NAME' pointed at the rootless socket"
if docker context inspect "$CONTEXT_NAME" >/dev/null 2>&1; then
    ok "context '$CONTEXT_NAME' already exists"
else
    docker context create "$CONTEXT_NAME" --docker "host=$USER_SOCK"
    done_ "created context '$CONTEXT_NAME' -> $USER_SOCK"
fi

# Smoke test ------------------------------------------------------------------
step "Smoke test"
if DOCKER_CONTEXT="$CONTEXT_NAME" docker info >/dev/null 2>&1; then
    ok "docker --context $CONTEXT_NAME info: rootless daemon reachable"
else
    warn "docker --context $CONTEXT_NAME info failed — check 'systemctl --user status docker'"
fi

echo
echo "Rootless Docker setup complete."
echo "Run 'uv run hallm cluster preflight' next; if any check fails, re-login (or reboot) and retry."
