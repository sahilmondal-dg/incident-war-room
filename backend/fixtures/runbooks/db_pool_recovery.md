---
title: DB Connection Pool Recovery
category: database
service_tags: [payments-api, orders-api]
last_updated: 2026-03-01
---

## Symptoms
- `HikariPool` or connection pool timeout errors in logs
- `Connection not available, timed out after Nms` messages
- High pool wait queue (idle=0, waiting>10)
- Increased p99 latency on database-backed endpoints

## Root Cause
Connection pool exhausted due to slow queries holding connections, misconfigured pool size, or a connection leak caused by unclosed transactions.

## Resolution Steps
1. Check pool metrics: `kubectl exec -it <pod> -- curl localhost:8080/actuator/metrics/hikaricp.connections`
2. Identify long-running queries: `SELECT pid, query, state, now() - query_start AS duration FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 20;`
3. Kill blocking queries if safe: `SELECT pg_terminate_backend(<pid>);`
4. Perform rolling restart to release leaked connections: `kubectl rollout restart deployment/<service-name>`
5. Wait for rollout: `kubectl rollout status deployment/<service-name>`
6. Increase pool size in config if traffic warrants: set `HIKARI_MAXIMUM_POOL_SIZE` env var and redeploy
7. Verify pool metrics return to normal after restart

## Verification
- Pool idle connections > 0 in actuator metrics
- No new `connection not available` errors in last 2 minutes
- p99 latency returns to baseline
