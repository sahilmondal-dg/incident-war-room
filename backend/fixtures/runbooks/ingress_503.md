---
title: Ingress 503 Service Unavailable Recovery
category: network
service_tags: [api-gateway, ingress-controller, payments-api]
last_updated: 2026-03-01
---

## Symptoms
- Clients receiving HTTP 503 Service Unavailable responses
- Ingress controller logs showing `no endpoints available for service`
- All or some backend pods failing health checks
- `Endpoints` object for the service showing empty or reduced address list

## Root Cause
The ingress controller cannot route traffic to backend pods because no pods are healthy (all failing readiness probes), the Endpoints object is stale, or the Service selector does not match any running pods.

## Resolution Steps
1. Check the Endpoints object for the service: `kubectl get endpoints <service-name> -n <namespace>`
2. If endpoints are empty, check pod readiness: `kubectl get pods -n <namespace> -l app=<service-name>`
3. Describe a failing pod to see readiness probe failures: `kubectl describe pod <pod-name> -n <namespace> | grep -A 10 Readiness`
4. Check pod logs for startup errors: `kubectl logs <pod-name> -n <namespace> --tail=50`
5. Verify Service selector matches pod labels: `kubectl get svc <service-name> -o jsonpath='{.spec.selector}'` vs `kubectl get pods --show-labels`
6. If selector is wrong (e.g., after a label change), patch the Service: `kubectl patch svc <service-name> -p '{"spec":{"selector":{"app":"<correct-label>"}}}'`
7. If pods are healthy but Endpoints is stale, restart kube-proxy: `kubectl rollout restart daemonset/kube-proxy -n kube-system`

## Verification
- `kubectl get endpoints <service-name>` shows the expected number of pod IPs
- Ingress controller logs show `successfully added backend` for the service
- HTTP 503 rate drops to zero within 1 minute
