---
title: Pod CrashLoopBackOff Recovery
category: kubernetes
service_tags: [payments-api, user-service, order-service, auth-service]
last_updated: 2026-03-01
---

## Symptoms
- Pod status shows `CrashLoopBackOff` in `kubectl get pods`
- Restart count incrementing rapidly
- Service degraded due to reduced pod availability
- Readiness probe failures causing pod removal from load balancer

## Root Cause
The container is starting and immediately exiting. Common causes: application startup exception, missing environment variable or secret, misconfigured readiness/liveness probe, or a failed init container.

## Resolution Steps
1. Identify crashing pods: `kubectl get pods -n <namespace> | grep CrashLoop`
2. Check the last crash reason: `kubectl describe pod <pod-name> -n <namespace> | grep -A 10 "Last State"`
3. View application logs from the last crash: `kubectl logs <pod-name> -n <namespace> --previous`
4. Check for missing secrets or configmaps: `kubectl describe pod <pod-name> | grep -E "Error|Warning|<none>"`
5. Verify all required environment variables are present: `kubectl exec -it <running-pod> -- env | sort`
6. If the issue is a bad config change, roll back the deployment: `kubectl rollout undo deployment/<service-name> -n <namespace>`
7. If the issue is a startup probe timeout, temporarily increase probe thresholds: `kubectl patch deployment <service-name> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container>","livenessProbe":{"failureThreshold":10}}]}}}}'`

## Verification
- All pods show `Running` and `1/1 READY`
- Restart count stops incrementing
- No `CrashLoopBackOff` in `kubectl get pods` output
