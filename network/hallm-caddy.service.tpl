[Unit]
Description=Caddy reverse proxy for hallm.local
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=root
ExecStart=##CADDY_BIN## run --config /etc/caddy/Caddyfile --adapter caddyfile
ExecReload=##CADDY_BIN## reload --config /etc/caddy/Caddyfile --adapter caddyfile --force
TimeoutStopSec=5s
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
