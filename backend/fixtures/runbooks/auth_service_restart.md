---
title: Auth Service Graceful Restart
category: auth
service_tags: [auth-service]
last_updated: 2026-03-01
---

## Symptoms
- Elevated 401/403 error rates from downstream services
- Token validation failures in auth-service logs
- `connection refused` or `upstream connect error` to identity-provider
- Auth-service pods showing high CPU or stuck threads

## Root Cause
Auth-service has entered a degraded state due to stale token caches, exhausted thread pool, or a failed connection to the upstream identity provider. A graceful restart clears in-memory state and re-establishes connections.

## Resolution Steps
1. Confirm the issue is in auth-service: `kubectl logs -n prod deployment/auth-service --tail=100 | grep -E "ERROR|WARN"`
2. Check upstream identity provider connectivity: `kubectl exec -it <auth-pod> -- curl -sv https://identity-provider.internal/health`
3. If identity provider is reachable, perform graceful rolling restart: `kubectl rollout restart deployment/auth-service -n prod`
4. Monitor rollout progress: `kubectl rollout status deployment/auth-service -n prod`
5. If rollout stalls (pods not becoming ready), check readiness probe: `kubectl describe pod <new-pod-name> -n prod`
6. Verify token issuance is working: `curl -X POST https://auth-service.internal/token -d '{"client_id":"test"}'`

## Verification
- All auth-service pods show `Running` and `1/1 READY`
- 401/403 error rate drops to < 0.1% within 2 minutes
- Downstream services report successful auth in their logs
