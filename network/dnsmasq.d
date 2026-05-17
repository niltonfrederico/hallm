address=/openclaw.hallm.local/127.0.0.2
# hallm.local answers with the tailnet IP so phones (and any tailnet peer)
# get a routable address. Traefik on this host binds 0.0.0.0:443, so the
# local browser also reaches https://*.hallm.local via tailscale0 — at the
# cost of depending on tailscaled being up.
address=/hallm.local/100.104.47.75
# Also listen on the tailnet interface so Tailscale Split DNS can forward
# *.hallm.local queries from peers (e.g. phone) to this dnsmasq.
listen-address=100.104.47.75
