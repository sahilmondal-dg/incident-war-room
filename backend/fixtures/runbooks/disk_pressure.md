---
title: Disk Pressure Recovery
category: infrastructure
service_tags: [logging-service, data-pipeline, postgres]
last_updated: 2026-03-01
---

## Symptoms
- Node condition `DiskPressure=True` in `kubectl describe node`
- Pods being evicted with reason `The node was low on resource: ephemeral-storage`
- Log ingestion pipeline stalling or dropping events
- PVC usage above 85% threshold alert firing

## Root Cause
Ephemeral storage on the node or a persistent volume has reached capacity. Common causes include unbounded log files, large temporary files from batch jobs, or a PVC that was not sized for growth.

## Resolution Steps
1. Identify affected node: `kubectl get nodes | grep DiskPressure`
2. Check disk usage on the node: `kubectl debug node/<node-name> -it --image=busybox -- df -h`
3. Find large directories: `kubectl debug node/<node-name> -it --image=busybox -- du -sh /host/var/log/* | sort -rh | head -20`
4. If container logs are the cause, truncate safely: `kubectl exec -it <pod> -- truncate -s 0 /var/log/app.log`
5. Delete completed or failed pods that leave ephemeral storage: `kubectl delete pods --field-selector=status.phase=Failed -A`
6. If PVC is full, expand it (if storage class supports expansion): `kubectl patch pvc <pvc-name> -p '{"spec":{"resources":{"requests":{"storage":"50Gi"}}}}'`
7. Cordon and drain the node if evictions are ongoing while PVC expands

## Verification
- Node disk usage below 75%
- `DiskPressure` condition resolves: `kubectl get node <node-name> -o jsonpath='{.status.conditions}'`
- No pod eviction events in last 10 minutes
