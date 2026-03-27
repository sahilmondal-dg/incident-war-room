---
title: Redis Memory Pressure Recovery
category: cache
service_tags: [session-service, cart-service, product-service]
last_updated: 2026-03-01
---

## Symptoms
- Redis `used_memory` approaching `maxmemory` limit
- `OOM command not allowed when used memory > maxmemory` errors (Redis OOM, not JVM)
- Eviction rate increasing: `evicted_keys` counter rising
- Application errors indicating failed cache writes

## Root Cause
Redis instance is running low on available memory due to large key volumes, unexpectedly large values, or TTL misconfiguration allowing keys to accumulate without expiry.

## Resolution Steps
1. Check current memory usage: `redis-cli -h <redis-host> INFO memory`
2. Identify large keys: `redis-cli -h <redis-host> --bigkeys`
3. Check key count and TTL distribution: `redis-cli -h <redis-host> INFO keyspace`
4. If keys are missing TTLs, set a default expiry on the largest keyset: `redis-cli -h <redis-host> SCAN 0 MATCH "session:*" COUNT 100` and apply TTL
5. Delete stale or orphaned keyspaces if safe: `redis-cli -h <redis-host> DEL <identified-large-keys>`
6. If memory is genuinely undersized, increase Redis `maxmemory` via the config map and restart: `kubectl rollout restart deployment/redis`
7. Switch eviction policy to `allkeys-lru` if not already set to prevent hard OOM: update `redis.conf` and restart

## Verification
- `used_memory` drops below 80% of `maxmemory`
- `evicted_keys` rate returns to zero or near-zero
- Application cache write errors stop appearing in logs
