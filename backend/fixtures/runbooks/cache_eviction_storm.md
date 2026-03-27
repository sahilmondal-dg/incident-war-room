---
title: Cache Eviction Storm Recovery
category: cache
service_tags: [product-service, search-service, recommendation-service]
last_updated: 2026-03-01
---

## Symptoms
- Sudden spike in database query rate following cache miss storm
- Cache hit ratio drops below 50% in Redis/Memcached metrics
- High DB CPU due to thundering herd of uncached requests
- Elevated response latency across services that rely on caching

## Root Cause
A large-scale cache eviction occurred due to a cache flush, TTL expiry storm, Redis maxmemory eviction policy kicking in, or a deployment that invalidated cache keys. All requests simultaneously hit the database.

## Resolution Steps
1. Confirm cache miss rate spike: check Redis `keyspace_misses` metric in monitoring
2. Check Redis memory usage: `redis-cli -h <redis-host> INFO memory | grep used_memory_human`
3. If Redis is evicting due to memory pressure, reduce TTL temporarily is NOT recommended — instead increase Redis memory allocation
4. Implement request coalescing at the application level if supported (dog-pile lock)
5. Pre-warm cache using the warm-up script: `kubectl run cache-warmer --image=<service-image> -- python scripts/cache_warmup.py`
6. Scale up the database horizontally to absorb read load: `kubectl scale deployment/postgres-read-replica --replicas=3`
7. Monitor cache hit ratio recovery: target > 80% hit rate before scaling back DB

## Verification
- Cache hit ratio exceeds 80% in Redis metrics
- Database CPU returns to baseline
- Service p99 latency normalises within 5 minutes of cache warm-up
