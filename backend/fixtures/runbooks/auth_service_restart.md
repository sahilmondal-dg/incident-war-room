---
title: Auth Service Graceful Restart
category: auth
service_tags: [auth-service]
last_updated: 2026-03-01
---

## Symptoms
- Elevated 401/403 error rates from downstream services
- Token validation failures and JWT signature errors in auth-service logs
- Auth-service pods showing high CPU, stuck threads, or OOMKilled restarts
- Stale token cache causing repeated re-validation failures
- Thread pool exhaustion: `No threads available in pool` in auth-service logs

## Root Cause
Auth-service has entered a degraded state due to stale token caches, exhausted thread pool, or in-memory state corruption. The upstream identity provider is reachable but the auth-service process itself needs a restart to clear internal state.

## Resolution Steps
1. Confirm the issue is in auth-service internals: `kubectl logs -n prod deployment/auth-service --tail=100 | grep -E "thread pool|cache|OOM|stale"`
2. Verify upstream identity provider IS reachable: `kubectl exec -it <auth-pod> -- curl -sv https://identity-provider.internal/health`
3. If identity provider is reachable (HTTP 200), perform graceful rolling restart: `kubectl rollout restart deployment/auth-service -n prod`
4. Monitor rollout progress: `kubectl rollout status deployment/auth-service -n prod`
5. If rollout stalls (pods not becoming ready), check readiness probe: `kubectl describe pod <new-pod-name> -n prod`
6. Verify token issuance is working: `curl -X POST https://auth-service.internal/token -d '{"client_id":"test"}'`

## Verification
- All auth-service pods show `Running` and `1/1 READY`
- 401/403 error rate drops to < 0.1% within 2 minutes
- Downstream services report successful auth in their logs
