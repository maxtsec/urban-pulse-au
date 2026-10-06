# Consumer-account IAP configuration checks

Date: 2026-10-06. Scope: [ADR 0013](../adr/0013-named-consumer-iap-access.md), [serving Terraform](../../infra/demo-serving), and the [OAuth/bootstrap procedure](../runbooks/managed-demo-serving.md#custom-oauth-bootstrap-and-operator-access). Progress is maintained in the [delivery plan](../delivery-plan.md).

The root defaults to a closed service with no reviewer binding. A later named-user grant requires a syntactically valid custom client ID in the private plan. The ID is an operator assertion; OAuth setup, secret handling, live read-back and consent status remain a separately reviewed Console bootstrap operation. There is no OAuth secret input or managed OAuth resource in this root.

Local verification:

- Readonly provider-lock initialization, tracked Terraform formatting, provider validation and 24 mocked plans passed. Consumer Gmail access is supported independently of project organization membership. The closed stage keeps IAP and its invoker check enabled without a reviewer resource; a named-user grant without a client record fails. Public, authenticated-public, domain, group, service-account, disguised service-account and null/malformed user principals are rejected. Existing runtime/secret/probe/scaling, image, candidate and rollback checks still pass.
- Ruff lint/format, mypy and all 549 unit tests passed. Application runtime and image packaging are unchanged; PostGIS integration and browser/Compose smoke were not rerun locally for this Terraform/documentation change.
- Local Markdown file targets resolve; `git diff --check` passed.
- These credential-free tests do not configure a real OAuth client, validate a consent screen or establish allowed/denied cloud browser behavior. Use the runbook for the actual service-scoped checks before enabling access.

No cloud resources, OAuth credentials or IAM bindings were changed by this work. Actual operator identity and deployment values remain private. The first saved plan now expects two additions; after OAuth bootstrap, the operator-access plan expects one additional binding with no service changes. Each plan has a separate approval gate.

Review follow-up: the runbook now gates first apply and OAuth setup on effective project domain-restricted-sharing evidence, with a Console read path when the API is unavailable. An unreadable or blocking policy stops the workflow. This documentation review did not verify live organization policies, enable the API or approve a policy exception.
