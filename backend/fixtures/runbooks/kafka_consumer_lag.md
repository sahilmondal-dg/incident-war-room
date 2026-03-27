---
title: Kafka Consumer Lag Recovery
category: messaging
service_tags: [data-pipeline, notification-service, audit-service]
last_updated: 2026-03-01
---

## Symptoms
- Kafka consumer group lag increasing continuously in monitoring
- Message processing delay exceeding SLA thresholds
- `Consumer group is rebalancing` log messages appearing frequently
- Dead letter queue (DLQ) accumulating messages

## Root Cause
Consumer lag is growing because consumers are processing messages slower than producers are publishing. Causes include slow message processing, consumer crashes causing frequent rebalancing, or a poison-pill message blocking a partition.

## Resolution Steps
1. Check consumer group lag: `kubectl exec -it <kafka-pod> -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group <consumer-group>`
2. Check for poison-pill messages: look for partitions where a single offset is stuck
3. If a partition is stuck, skip the problematic offset: `kubectl exec -it <kafka-pod> -- kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group <consumer-group> --topic <topic> --reset-offsets --to-offset <stuck-offset+1> --execute`
4. Reduce consumer rebalance frequency by increasing `session.timeout.ms` and `heartbeat.interval.ms` in consumer config
5. Scale up consumer replicas to increase throughput: `kubectl scale deployment/<consumer-service> --replicas=<N>`
6. Check DLQ for failed messages and decide whether to replay or discard: `kubectl exec -it <kafka-pod> -- kafka-console-consumer.sh --topic <dlq-topic> --from-beginning --max-messages 10`

## Verification
- Consumer lag is decreasing in monitoring
- No active rebalancing events in consumer logs
- Lag reaches zero or stabilises at acceptable level within 10 minutes
