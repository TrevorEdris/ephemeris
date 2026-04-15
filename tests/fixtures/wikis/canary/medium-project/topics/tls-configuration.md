# TLS Configuration

## Overview
Orchid terminates external TLS at the gateway boundary. Internal service-to-
service communication uses mTLS enforced by the cluster service mesh.

## Details

### 2026-02-10 (session-or003)
External TLS certificates are managed by cert-manager with Let's Encrypt as
the ACME provider. Certificate renewal is automatic; cert-manager handles
DNS-01 challenges for wildcard certificates.

### 2026-02-18 (session-or005)
mTLS internal: each backend service has a certificate issued by the cluster
internal CA. Orchid presents its own client certificate when forwarding
requests. Backend services reject requests without a valid client certificate.

Certificate rotation for internal certs happens every 7 days automatically.
Services pick up the new certificate on the next connection attempt without
restart.

## Sessions
> Source: [2026-02-10 session-or003]
> Source: [2026-02-18 session-or005]
