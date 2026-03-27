---
title: Upstream Service Timeout Recovery
category: network
service_tags: [api-gateway, payments-api, order-service]
last_updated: 2026-03-01
---

## Symptoms
- `upstream request timeout` or `context deadline exceeded` in logs
- Elevated 504 Gateway Timeout responses to clients
- Specific upstream service showing high latency in service mesh metrics
- Circuit breaker opening on the upstream dependency

## Root Cause
An upstream dependency is responding too slowly, causing the calling service to time out. This may be due to the upstream being overloaded, a slow database query on the upstream, or a network issue between the two services.

## Resolution Steps
1. Identify the slow upstream: check service mesh or APM traces for the highest-latency span
2. Check the upstream service health: `kubectl get pods -n <namespace> -l app=<upstream-service>`
3. Review the upstream service logs for slow query or processing warnings: `kubectl logs deployment/<upstream-service> --tail=100 | grep -E "slow|timeout|latency"`
4. If the upstream is overloaded, scale it up: `kubectl scale deployment/<upstream-service> --replicas=<N>`
5. If a single slow endpoint is causing cascading timeouts, consider temporarily routing around it or returning a degraded response
6. Increase the caller's timeout threshold if the upstream is slow but functional and the operation is critical: update config and rolling-restart the caller
7. If the upstream is in a death spiral, restart it: `kubectl rollout restart deployment/<upstream-service>`

## Verification
- Upstream p99 latency returns to baseline in service mesh metrics
- 504 error rate drops to < 0.1%
- No circuit breaker open events in last 3 minutes
