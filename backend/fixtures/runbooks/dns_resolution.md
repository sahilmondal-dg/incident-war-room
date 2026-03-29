---
title: DNS Resolution Failure
category: network
service_tags: [auth-service, api-gateway]
last_updated: 2026-03-01
---

## Symptoms
- `getaddrinfo NXDOMAIN` or `DNS lookup failure` for internal hostnames (e.g. `identity-provider.internal`)
- Upstream provider reported as unreachable due to DNS resolution failure — not a service outage
- Services unable to reach internal endpoints: `Name or service not known`, `no address associated with hostname`
- Auth or API services showing cascade failures because identity-provider or upstream DNS is not resolving
- Circuit breakers opening on services that depend on DNS-resolved internal hostnames
- Token validation or OAuth2 failures caused by DNS lookup failure to identity-provider
- 5xx error rate elevated on services that connect to other services by hostname
- `upstream connect error` caused by underlying DNS lookup failure rather than the upstream service itself being down

## Root Cause
CoreDNS pods may be crashing, overloaded, or the cluster DNS ConfigMap is misconfigured. Alternatively, a service name was changed or removed without updating DNS entries. The upstream service itself is healthy — DNS resolution is the failure point causing cascading auth and connectivity errors.

## Resolution Steps
1. Check CoreDNS pod health: `kubectl get pods -n kube-system -l k8s-app=kube-dns`
2. Check CoreDNS logs for errors: `kubectl logs -n kube-system -l k8s-app=kube-dns --tail=50`
3. Test DNS from an affected pod: `kubectl exec -it <pod> -- nslookup identity-provider.internal`
4. Restart CoreDNS if pods are in CrashLoopBackOff: `kubectl rollout restart deployment/coredns -n kube-system`
5. Flush DNS cache on affected pods: `kubectl exec -it <pod> -- killall -HUP dnsmasq` (if dnsmasq is present)
6. Verify service DNS entries exist: `kubectl get svc -n <namespace> | grep <expected-service>`
7. If service is missing, recreate it from the Helm chart or manifests in the repo

## Verification
- `nslookup identity-provider.internal` resolves successfully from affected pods
- CoreDNS pods are Running with 0 restarts
- Application-level 5xx error rate and auth failures return to baseline within 2 minutes
