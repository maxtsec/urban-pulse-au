# ADR 0013: Named consumer accounts for the fixture demo

Date: 2026-10-06

Status: **Accepted by the project architect on 2026-10-06.** Supersedes only the organization-only audience in [ADR 0012](0012-managed-demo-resource-profile.md). Hosting, database, runtime identities and apply approval gates remain governed by [ADR 0010](0010-hosted-fixture-demo.md) and ADR 0012.

## Context and decision

The acceptance operator uses a consumer Google account. Google-managed IAP OAuth is limited to organization users, so that profile cannot support the intended browser login. Use a dedicated custom Web OAuth client with an External consent audience, while retaining direct Cloud Run IAP and explicit service-scoped access. [Cloud Run IAP access](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run#manage-user-group-access).

Initially allow only the named acceptance operator. Keep the actual address in private deployment configuration. Later reviewer additions require a separate access review; the initial configuration accepts named users, not groups, domain grants or public principals. An External OAuth audience permits consumer authentication; it does not grant application access. IAP IAM remains the authorization boundary.

## Provisioning and credential ownership

Create the protected service first with no reviewer binding, then configure custom OAuth at that service through a separately reviewed Console bootstrap step. Keep the client secret outside Terraform inputs, plan/state, images and GitHub. The operator owns the OAuth credential lifecycle; any retained credential copy belongs in approved private secret storage. Record the non-secret client ID and sanitized settings evidence. OAuth is not managed by the serving Terraform root.

Only after verifying the service-scoped OAuth configuration, consent setup and inherited IAM should a second saved plan grant the named operator IAP access. The client ID in Terraform is a deployment assertion, not proof of live settings. Use the [runbook](../runbooks/managed-demo-serving.md#custom-oauth-bootstrap-and-operator-access) for the review and read-back sequence. No bootstrap, IAM mutation or resource apply is authorized merely by merging this decision.

## Consequences

The first serving plan creates two resources (service and IAP-agent invoker binding); the operator-access plan adds the third (reviewer binding). There is no public interval between them: IAP remains enabled with its invoker check throughout, and inherited IAP accessor grants must be absent. A project organization and matching email domain are no longer login prerequisites, but ancestry still needs inspection for inherited IAM and organization policies.

Custom OAuth adds consent-screen configuration, secret rotation and drift checks outside Terraform. A clean Terraform plan cannot establish OAuth correctness. Before opening access, and before later deployment acceptance, verify the recorded client/settings and exercise allowed and denied browser logins. OAuth testing/publication limits must be checked in the actual Google Auth Platform configuration; wider distribution is a separate review. Closing the Terraform allowlist removes its managed binding but cannot revoke inherited grants.
