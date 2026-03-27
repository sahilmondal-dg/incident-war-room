---
title: HPA Scaling Failure Recovery
category: kubernetes
service_tags: [payments-api, api-gateway, search-service]
last_updated: 2026-03-01
---

## Symptoms
- HPA not scaling pods despite high CPU or memory metrics
- `kubectl get hpa` shows `<unknown>` for current metrics
- `FailedGetScale` or `unable to fetch metrics` events in HPA
- Service degraded under load with pod count stuck at minimum

## Root Cause
The Horizontal Pod Autoscaler cannot retrieve metrics from the metrics-server, or the metrics-server is not running. Alternatively, resource requests are not set on the deployment, preventing HPA from calculating utilisation.

## Resolution Steps
1. Check HPA status and events: `kubectl describe hpa <hpa-name> -n <namespace>`
2. Verify metrics-server is running: `kubectl get deployment metrics-server -n kube-system`
3. Check metrics-server logs for errors: `kubectl logs -n kube-system deployment/metrics-server --tail=50`
4. If metrics-server is down, restart it: `kubectl rollout restart deployment/metrics-server -n kube-system`
5. Verify resource requests are set on the target deployment: `kubectl get deployment <service-name> -o jsonpath='{.spec.template.spec.containers[*].resources}'`
6. If requests are missing, patch the deployment to add them: `kubectl set resources deployment/<service-name> --requests=cpu=100m,memory=256Mi`
7. Manually scale temporarily while HPA recovers: `kubectl scale deployment/<service-name> --replicas=<N>`

## Verification
- `kubectl get hpa` shows numeric values for TARGETS column
- HPA scales pods up as CPU/memory rises above threshold
- No `FailedGetScale` events in last 5 minutes
