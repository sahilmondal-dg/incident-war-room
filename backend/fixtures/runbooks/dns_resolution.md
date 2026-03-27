---
title: DNS Resolution Failure
category: network
service_tags: [auth-service, api-gateway]
last_updated: 2026-03-01
---

## Symptoms
- `DNS resolution failed for <hostname>` errors in logs
- `upstream connect error or disconnect/reset before headers`
- Services unable to reach internal endpoints by DNS name
- 5xx error rate elevated on services that depend on internal DNS

## Root Cause
CoreDNS pods may be crashing, overloaded, or the cluster DNS ConfigMap is misconfigured. Alternatively, a service name was changed without updating DNS entries.

## Resolution Steps
1. Check CoreDNS pod health: `kubectl get pods -n kube-system -l k8s-app=kube-dns`
2. Check CoreDNS logs for errors: `kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50`
3. Restart CoreDNS if pods are in CrashLoopBackOff: `kubectl rollout restart deployment/coredns -n kube-system`
4. Flush DNS cache on affected pods: `kubectl exec -it <pod> -- killall -HUP dnsmasq` (if dnsmasq is present)
5. Verify service DNS entries exist: `kubectl exec -it <pod> -- nslookup <service-name>.<namespace>.svc.cluster.local`
6. Check for missing Service resources: `kubectl get svc -n <namespace> | grep <expected-service>`
7. If service is missing, recreate it from the Helm chart or manifests in the repo

## Verification
- `nslookup` resolves all internal service hostnames successfully
- CoreDNS pods are Running with 0 restarts
- 5xx error rate returns to baseline within 2 minutes of fix
