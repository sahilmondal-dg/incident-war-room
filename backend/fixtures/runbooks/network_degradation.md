---
title: Network Degradation Recovery
category: network
service_tags: [api-gateway, payments-api, order-service]
last_updated: 2026-03-01
---

## Symptoms
- Elevated inter-service latency across multiple services simultaneously
- Packet loss detected in network probes
- `context deadline exceeded` or `i/o timeout` errors in service logs
- Traffic dropping between availability zones

## Root Cause
Network fabric issue, overloaded network interface on a node, or misconfigured network policy causing packet drops between pods or nodes.

## Resolution Steps
1. Confirm network scope: check if degradation is cross-AZ or within a single node: `kubectl get nodes -o wide`
2. Identify affected nodes via node metrics: check network TX/RX error counters in Cloud Console
3. Cordon the suspect node to stop new pods being scheduled: `kubectl cordon <node-name>`
4. Drain the node gracefully: `kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data`
5. Verify pods rescheduled on healthy nodes: `kubectl get pods -o wide | grep -v Running`
6. Check NetworkPolicy objects for recent changes: `kubectl get networkpolicy -A`
7. If NetworkPolicy was recently modified, roll back: `kubectl rollout undo deployment/<affected-service>`
8. Re-enable the node once network is confirmed healthy: `kubectl uncordon <node-name>`

## Verification
- Inter-service p99 latency returns to baseline
- No packet loss in network probes for 5 consecutive minutes
- All pods Running on healthy nodes
