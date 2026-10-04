# ADR 0001: An integrated Melbourne city intelligence product

Status: accepted product direction. Date: 4 October 2026.

## Context

Residents need to understand current city conditions alongside longer-term area context. Transport, weather and planning have different spatial coverage, validity and update cadences; the product must combine them without losing those distinctions.

## Decision

The product integrates Transport, Weather & Hazards, and Planning & Infrastructure through a Location Intelligence boundary. Its MVP includes a narrow, evidence-supported slice of all three inputs in a map and area panel.

Transport can be the first implementation slice. A standalone transport dashboard does not complete the MVP. Separate current conditions from longer-term area context; expose coverage, validity and source dates.

Use a modular backend and independent worker approach. Domain boundaries do not imply separate deployed microservices. Use the selected GCP and operational/analytical technology foundation.

Run minimal continuous raw capture as a parallel track targeting phases 1-2 so historical analysis has retained inputs. Source/cloud readiness does not gate phase 1 fixture completion. Agree the event envelope in phase 1, use it through an in-process adapter in phase 2, and add durable delivery/recovery in phase 3. Full application cloud deployment is a separate phase 4 concern; historical analysis follows in phase 5.

## Alternatives and consequences

A transport-only MVP would reach a deep single-domain demo sooner but would not demonstrate the integrated product. Building every source, a full warehouse and scoring engine first would delay a useful city view. A small integrated slice exposes spatial, temporal and source-coverage constraints early.

Source feasibility can constrain the first area. Warehouse depth, numerical scores and evaluated AI tools follow the city MVP. Security, tests, traceability and basic recovery remain requirements throughout.

## Open implementation decisions

[ADR 0002](0002-southbank-tram-pilot.md) selects the pilot boundary source and initial transport scope. Provider terms, boundary-edge rules, map tiles, field-level contracts, status thresholds, durable transport and cloud host/region/budget remain in the [decision queue](../delivery-plan.md#decisions-needed-before-dependent-work). Resolve A-06 at the start of phase 1 for early capture.

Revisit scope if official source coverage cannot support a useful common area, or demonstrations show the combined view does not meet the stated user need.
