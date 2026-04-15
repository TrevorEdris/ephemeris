# Request Routing

## Overview
Orchid routes inbound requests to backend services based on path prefixes and
host headers. Routing rules are defined in a YAML configuration file that is
hot-reloaded without gateway restart.

## Details

### 2026-02-12 (session-or004)
Routing configuration file: `orchid.routes.yaml`. Changes are picked up within
5 seconds via inotify watch. A config parse error leaves the previous routing
table in effect and logs a warning.

Route matching order:
1. Exact path match
2. Longest prefix match
3. Host-header match
4. Default backend (if configured)

If no route matches and no default backend is configured, Orchid returns
HTTP 404 with a JSON body: `{"error": "no route found"}`.

### 2026-02-22 (session-or006)
Canary routing: a route can specify a `canary_weight` (0–100) to send a
percentage of traffic to a canary backend while the remainder goes to the
stable backend. Canary decisions are sticky per client IP within a session.

## Sessions
> Source: [2026-02-12 session-or004]
> Source: [2026-02-22 session-or006]
