# Agent Security and Availability Design

## Goal

Close the Agent service authorization, confirmation, billing, and discovery gaps identified in the audit, and make Agent dialogue reachable through the gateway. Existing short-drama records without an owner are intentionally quarantined.

## Scope

- The Node/Pi service at `pi-main/packages/vibepaper-agent-service` is the only supported Agent runtime.
- The legacy root `agent-service` Python implementation is removed after its currently-used configuration values are represented by the Node service sample configuration.
- Existing `drama_*` records are not assigned to any user. The migration sets no usable ownership and all public drama operations reject those records. A future administrative recovery flow is outside this change.

## Availability and service discovery

The 503 is caused by agent-service not registering in Nacos: its runtime environment has no Nacos credentials and the Node registrar returns early, while the gateway route is `lb://agent-service`.

The Node configuration will use the same development Nacos defaults as generation-service (`nacos`/`nacos`), while production requires explicitly configured credentials and an internal-service token. The registrar will log login, registration, heartbeat, and deregistration failures; it will reattempt registration on heartbeat failure. Startup will fail in production if either required setting is absent. The sample environment file will include the correct admin-service port (8087), Nacos settings, and an explicit internal token placeholder.

## Ownership and data model

Schema setup is replaced by ordered SQL migrations recorded in `schema_migrations`. The baseline creates existing tables; the next migration adds `drama_series.user_id BIGINT`, an owner/canvas index, and a `legacy_unowned` state. The migration leaves every pre-existing series unowned. It does not derive ownership from another service database.

`DramaSeries` and `PgDramaStateStore` receive `userId`. Every store method that resolves a series, character, shot, reference pack, keyframe, or lineage accepts the calling user and reaches the series through an owner-filtered query. A missing or foreign record returns `NOT_FOUND`, avoiding resource enumeration. New series use the caller's user ID; all dependent writes first validate the owned ancestor. New server-generated domain IDs use `nextId()` and continue to fit the existing `VARCHAR(64)` foreign keys.

## Confirmation and billing execution

Create an `ApprovalService` that serializes an action payload deterministically, hashes it with SHA-256, persists `agent_actions` plus `agent_approvals`, and issues an HMAC token bound to user, session, canvas, canvas version, hash, nonce, and expiry. The service decides `requiresConfirmation` from the PRD thresholds: estimated cost at least one, model change, numeric parameter change at least 30%, more than 20 created nodes, existing-output replacement, and destructive operations.

The confirmation endpoint locks and loads the pending action and approval in one transaction, verifies token/expiry/hash/user/session, obtains the current canvas version through the Tool Gateway, rejects a changed version with `VERSION_CONFLICT`, consumes the approval exactly once, and invokes the stored executor. Generation submission is available only through this executor: create the canvas node, submit to billing with an idempotency key, then update node state. A canvas-node update failure is logged with request, canvas, node, and task identifiers and is surfaced as an explicit retryable operation error rather than swallowed.

The immediate drama routes remain low-risk preparation/recording endpoints; keyframe/video generation becomes a proposed action whenever estimated cost is at least one. The response shape exposes `actionId`, `approvalToken`, expiry, action summary, and cost until confirmation. Direct generation submission routes do not exist.

## Streaming and API behavior

`runDramaTurn` accepts an event sink. The Fastify message route sends SSE headers and flushes each runtime event as it arrives, while separately collecting final assistant text and usage for persistence. `message_update` emits delta content rather than repeated full assistant text; `message_end` only emits final usage. The frontend appends deltas to the current turn.

The gateway route includes `/api/v1/drama/**` and `/api/v1/render-reviews/**` so these owned Agent endpoints are reachable under the same JWT boundary.

## Reliability and cleanup

- Snowflake generation waits for the next millisecond when the 12-bit sequence is exhausted and rejects clock rollback.
- Built-in skills are seeded once during service initialization, not per request. Skill input IDs are deduplicated before ownership validation.
- A single named history limit is used for both database read and model context selection.
- The unused Redis dependency and configuration field are removed because confirmation state is persisted in PostgreSQL in this implementation.
- `agent_sessions.skill_id` is removed in a migration because the service uses `skill_snapshot`.

## Verification

Tests cover Nacos configuration and registrar failures, migration ordering, owner isolation, legacy-record denial, approval threshold and token validation, canvas-version invalidation, one-time consumption, billing-only generation submission, node-update failure observability, SSE delta behavior, ID overflow/rollback, and duplicate Skill IDs. The existing package suite, TypeScript build, and a live Nacos registration/gateway Agent request check provide final evidence.
