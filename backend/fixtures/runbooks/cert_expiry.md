---
title: TLS Certificate Expiry Recovery
category: security
service_tags: [api-gateway, auth-service, ingress-controller]
last_updated: 2026-03-01
---

## Symptoms
- `certificate has expired or is not yet valid` in service logs
- Clients receiving TLS handshake errors
- `SSL_ERROR_RX_RECORD_TOO_LONG` or `ERR_CERT_DATE_INVALID` in browser
- cert-manager certificate resource showing `Ready=False`

## Root Cause
A TLS certificate managed by cert-manager or stored as a Kubernetes Secret has expired or is about to expire, and automatic renewal failed due to ACME challenge issues or DNS propagation delay.

## Resolution Steps
1. Identify expired certificates: `kubectl get certificate -A | grep False`
2. Describe the failing certificate for error details: `kubectl describe certificate <cert-name> -n <namespace>`
3. Check cert-manager logs for renewal errors: `kubectl logs -n cert-manager deployment/cert-manager --tail=100`
4. If ACME HTTP-01 challenge is failing, verify the ingress path `/.well-known/acme-challenge/` is reachable
5. Force certificate renewal by deleting the secret (cert-manager will re-issue): `kubectl delete secret <tls-secret-name> -n <namespace>`
6. Monitor re-issuance: `kubectl get certificate -n <namespace> -w`
7. If using a manually managed cert, upload the renewed cert: `kubectl create secret tls <tls-secret-name> --cert=tls.crt --key=tls.key --dry-run=client -o yaml | kubectl apply -f -`

## Verification
- Certificate `Ready=True`: `kubectl get certificate -A`
- TLS handshake succeeds: `openssl s_client -connect <hostname>:443 </dev/null 2>&1 | grep 'Verify return code'`
- No TLS errors in ingress-controller logs
