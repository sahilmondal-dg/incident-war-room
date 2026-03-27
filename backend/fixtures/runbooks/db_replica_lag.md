---
title: Database Replica Lag Recovery
category: database
service_tags: [payments-api, orders-api, reporting-service]
last_updated: 2026-03-01
---

## Symptoms
- Read replica lag exceeds threshold (typically > 30 seconds)
- Stale reads reported by users or detected in integration tests
- `replication_delay_seconds` metric spiking in database monitoring
- Replica falling behind primary in `pg_stat_replication`

## Root Cause
The read replica is unable to keep up with the primary's write-ahead log (WAL) replay rate. Causes include high write load on primary, a long-running transaction blocking WAL replay, or network latency between primary and replica.

## Resolution Steps
1. Check current replication lag: `psql -h <primary-host> -U admin -c "SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn, (sent_lsn - replay_lsn) AS replication_lag FROM pg_stat_replication;"`
2. Check for long-running transactions blocking WAL replay on the replica: `psql -h <replica-host> -U admin -c "SELECT pid, query, state, now() - pg_last_xact_replay_timestamp() AS replay_lag FROM pg_stat_activity WHERE state != 'idle';"`
3. Kill any long-running queries on the replica that are blocking replay: `SELECT pg_terminate_backend(<pid>);`
4. If write load on primary is the cause, throttle batch jobs: identify and pause non-critical batch jobs during peak
5. Route read traffic away from the lagging replica temporarily: update service config to point read queries at the primary
6. If the replica is too far behind to catch up, consider rebuilding it from a recent snapshot
7. Notify the DB team for ongoing lag exceeding 5 minutes

## Verification
- `replication_delay_seconds` metric drops below 5 seconds
- `pg_stat_replication.replay_lsn` approaches `sent_lsn` on the primary
- Read queries return up-to-date data
