---
title: Rate Limit Breach Response
category: traffic
service_tags: [api-gateway, payments-api, auth-service]
last_updated: 2026-03-01
---

## Symptoms
- Elevated HTTP 429 error rate in API gateway metrics
- `rate limit exceeded` messages in service logs
- Specific client IP or API key appearing in top-N request logs
- Downstream services reporting rejected requests

## Root Cause
A client, bot, or internal service is exceeding the configured request rate limit. This may be intentional (abuse) or accidental (misconfigured retry logic causing a retry storm).

## Resolution Steps
1. Identify the offending client: check API gateway access logs for top requesters by IP or API key
2. Verify it is not a legitimate traffic spike from a marketing event or deployment
3. If it is a retry storm from an internal service, identify the source: `kubectl logs deployment/<service> | grep "retry" | head -50`
4. Apply a temporary IP or key block at the gateway if abuse is confirmed
5. If it is a legitimate spike, temporarily increase rate limits: update the gateway ConfigMap and apply: `kubectl apply -f config/ratelimit.yaml`
6. If it is a retry storm, patch the offending deployment to add exponential backoff or circuit-breaker
7. Alert the platform team to review rate limit thresholds for the upcoming period

## Verification
- HTTP 429 rate drops below 0.1% of total requests
- No single client exceeds 10% of total request share
- Downstream services report normal acceptance rate
