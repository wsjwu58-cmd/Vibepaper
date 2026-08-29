import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";

import multipart from "@fastify/multipart";
import Fastify, { type FastifyInstance, type FastifyReply, type FastifyRequest } from "fastify";
import type { QueryResultRow } from "pg";

import {
	AgentRuntimeError,
	type AgentSkillContext,
	type AgentTurnEvent,
	runDramaTurn,
	type StoredAgentMessage,
} from "../application/agent-runtime.ts";
import {
	MAX_NODE_REFERENCES,
	NodeReferenceContextError,
	type NodeReferenceSnapshot,
} from "../application/node-reference-context.ts";
import type { ServiceConfig } from "../config.ts";
import {
	type CharacterProfile,
	type CharacterReferencePack,
	DramaDomainError,
	type DramaSeries,
	type KeyframeRender,
	type RenderLineage,
	type ShotSpec,
	STANDARD_VERTICAL_SHORT_DRAMA_FORMAT,
} from "../domain/drama-state.ts";
import { SYSTEM_SKILLS, skillIndexLine } from "../domain/skill-manifest.ts";
import type { SqlExecutor } from "../infrastructure/database.ts";
import { nextId } from "../infrastructure/ids.ts";
import { PgDramaStateStore } from "../infrastructure/pg-drama-state-store.ts";
import { ToolGateway, ToolGatewayError } from "../infrastructure/tool-gateway.ts";

type SessionRow = {
	id: string;
	title: string;
	canvas_id: string | null;
	status: string;
	token_used_total: number;
	points_used_total: number;
	model_usage: unknown;
	updated_at: Date;
};
type MessageRow = {
	id: string;
	role: "user" | "assistant" | "system";
	msg_type: string;
	content: string;
	meta: unknown;
	created_at: Date;
};
type SkillRow = {
	id: string;
	owner_id: string;
	name: string;
	description: string | null;
	instructions: string;
	source: string;
	category: string;
	version: number;
	enabled: boolean;
	created_at: Date;
	updated_at: Date;
};
type MemoryRow = { id: string; content: string; memory_type: string; created_at: Date };
type FragmentRow = { id: string; title: string | null; canvas_id: string | null; content: unknown; created_at: Date };

export interface CreateAppOptions {
	config: ServiceConfig;
	database: SqlExecutor;
	referenceGateway?: NodeReferenceGateway;
	runTurn?: typeof runDramaTurn;
}

export interface NodeReferenceGateway {
	getNodeReferences(
		userId: string,
		canvasId: string,
		nodeIds: readonly string[],
	): Promise<NodeReferenceSnapshot[]>;
}

export function createApp(options: CreateAppOptions): FastifyInstance {
	const app = Fastify({ logger: true });
	const { config, database } = options;
	const dramaState = new PgDramaStateStore(database);
	const referenceGateway = options.referenceGateway ?? new ToolGateway(config);
	const runTurn = options.runTurn ?? runDramaTurn;
	app.register(multipart, { limits: { fileSize: 512 * 1024, files: 1 } });

	app.setErrorHandler((error, _request, reply) => {
		const domainError = error instanceof DramaDomainError || error instanceof AgentRuntimeError;
		const referenceError = error instanceof NodeReferenceContextError;
		const gatewayError = error instanceof ToolGatewayError;
		const apiError = error instanceof ApiError;
		const known = domainError || referenceError || gatewayError || apiError;
		const status = referenceError
			? error.code === "NOT_FOUND"
				? 404
				: 400
			: gatewayError || apiError
				? error.statusCode
				: domainError
					? 400
					: isStatusError(error)
						? error.statusCode
						: 500;
		const code = known && "code" in error && typeof error.code === "string"
			? error.code
			: status === 500
				? "INTERNAL_ERROR"
				: "INVALID_INPUT";
		const message = error instanceof Error ? error.message : "未知服务错误";
		void reply.status(status).send({
			code,
			message,
			details: gatewayError ? error.details : undefined,
			request_id: reply.request.id,
			retryable: status >= 500,
		});
	});

	app.get("/health", async () => ({ status: "ok", service: config.appName, runtime: "pi-agent" }));

	app.post("/api/v1/agent/sessions", async (request, reply) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const id = nextId();
		const canvasId = optionalId(body.canvasId ?? body.canvas_id);
		const title = optionalString(body.title) ?? "新对话";
		await database.query(
			`INSERT INTO agent_sessions (id, user_id, canvas_id, title, model_usage)
			 VALUES ($1, $2, $3, $4, '{}'::jsonb)`,
			[id, userId, canvasId, title],
		);
		return await reply.status(201).send({ sessionId: id, title, canvasId });
	});

	app.get("/api/v1/agent/sessions", async (request) => {
		const userId = requireUserId(request);
		const query = request.query as { canvasId?: string };
		const canvasId = optionalId(query.canvasId);
		const rows = await database.query<SessionRow>(
			`SELECT id, title, canvas_id, status, token_used_total, points_used_total, model_usage, updated_at
			 FROM agent_sessions WHERE user_id = $1 AND ($2::bigint IS NULL OR canvas_id = $2::bigint)
			 ORDER BY updated_at DESC LIMIT 100`,
			[userId, canvasId],
		);
		return { items: rows.rows.map(sessionView) };
	});

	app.get("/api/v1/agent/sessions/:sessionId", async (request) => {
		const session = await requireSession(database, requireUserId(request), routeId(request, "sessionId"));
		return { sessionId: session.id, title: session.title, canvasId: session.canvas_id, status: session.status };
	});

	app.get("/api/v1/agent/sessions/:sessionId/messages", async (request) => {
		const sessionId = routeId(request, "sessionId");
		await requireSession(database, requireUserId(request), sessionId);
		const rows = await database.query<MessageRow>(
			"SELECT id, role, msg_type, content, meta, created_at FROM agent_messages WHERE session_id = $1 ORDER BY id",
			[sessionId],
		);
		return {
			items: rows.rows.map((message) => ({
				id: message.id,
				role: message.role,
				type: message.msg_type,
				content: message.content,
				meta: objectOrEmpty(message.meta),
				createdAt: message.created_at.toISOString(),
			})),
		};
	});

	app.post("/api/v1/agent/sessions/:sessionId/messages", async (request, reply) => {
		const userId = requireUserId(request);
		const sessionId = routeId(request, "sessionId");
		const body = recordBody(request.body);
		const content = requiredString(body.content, "content");
		let session = await requireSession(database, userId, sessionId);
		const requestedCanvas = optionalId(body.canvasId ?? body.canvas_id);
		if (requestedCanvas && requestedCanvas !== session.canvas_id) {
			await database.query("UPDATE agent_sessions SET canvas_id = $1, updated_at = now() WHERE id = $2", [
				requestedCanvas,
				sessionId,
			]);
			session = { ...session, canvas_id: requestedCanvas };
		}
		if (!session.canvas_id) throw new ApiError(400, "INVALID_INPUT", "会话未绑定画布，请在画布页重新打开 Agent");
		const selectedNodeIds = uniqueStrings(stringArray(body.selectedNodeIds)
			.map((id) => optionalId(id))
			.filter((id): id is string => id !== undefined));
		if (selectedNodeIds.length > MAX_NODE_REFERENCES) {
			throw new NodeReferenceContextError("INVALID_INPUT", `每轮最多引用 ${MAX_NODE_REFERENCES} 个节点`);
		}
		const nodeReferences = await referenceGateway.getNodeReferences(userId, session.canvas_id, selectedNodeIds);
		await addMessage(database, sessionId, "user", content, { selectedNodeIds, nodeReferences });
		await database.query(
			"UPDATE agent_sessions SET title = CASE WHEN title IN ('新对话', '画布对话') THEN $1 ELSE title END, updated_at = now() WHERE id = $2",
			[content.slice(0, 48), sessionId],
		);
		const history = await readHistory(database, sessionId);
		const skillContext = await resolveSkillContext(database, userId, sessionId);
		const outcome = await runTurn(
			config,
			dramaState,
			sessionId,
			history.slice(0, -1),
			content,
			skillContext,
			nodeReferences,
		);
		if (outcome.assistantText) await addMessage(database, sessionId, "assistant", outcome.assistantText, {});
		await database.query(
			`UPDATE agent_sessions SET token_used_total = token_used_total + $1,
				model_usage = jsonb_set(model_usage, '{assistant}', to_jsonb(COALESCE((model_usage->>'assistant')::integer, 0) + $1)), updated_at = now()
			 WHERE id = $2`,
			[outcome.totalTokens, sessionId],
		);
		return sendSse(reply, outcome.events);
	});

	app.get("/api/v1/agent/sessions/:sessionId/usage", async (request) => {
		const session = await requireSession(database, requireUserId(request), routeId(request, "sessionId"));
		return {
			sessionId: session.id,
			tokenTotal: session.token_used_total,
			pointsUsed: session.points_used_total,
			modelUsage: objectOrEmpty(session.model_usage),
		};
	});

	app.get("/api/v1/agent/sessions/:sessionId/skills", async (request) => {
		const userId = requireUserId(request);
		const sessionId = routeId(request, "sessionId");
		await requireSession(database, userId, sessionId);
		const context = await resolveSkillContext(database, userId, sessionId);
		return { index: context.indexLines, loadedSkillIds: context.loadedSkillIds };
	});

	app.put("/api/v1/agent/sessions/:sessionId/skills", async (request) => {
		const userId = requireUserId(request);
		const sessionId = routeId(request, "sessionId");
		await requireSession(database, userId, sessionId);
		const skillIds = stringArray(recordBody(request.body).skillIds);
		await ensureBuiltinSkills(database);
		const skills = await database.query<{ id: string; source: string }>(
			"SELECT id, source FROM skills WHERE id = ANY($1::bigint[]) AND enabled = true AND (owner_id = 0 OR owner_id = $2)",
			[skillIds, userId],
		);
		if (skills.rows.length !== skillIds.length || skills.rows.some((skill) => skill.source === "builtin")) {
			throw new ApiError(400, "INVALID_INPUT", "只能启用当前用户可用的动态 Skill");
		}
		await database.query(
			"UPDATE agent_sessions SET skill_snapshot = $1::jsonb, loaded_skill_ids = '[]'::jsonb, updated_at = now() WHERE id = $2",
			[JSON.stringify(skillIds), sessionId],
		);
		return { sessionId, skillIds };
	});

	app.post("/api/v1/agent/sessions/:sessionId/confirmations/:actionId", async (request) => {
		const userId = requireUserId(request);
		const sessionId = routeId(request, "sessionId");
		const actionId = routeId(request, "actionId");
		const body = recordBody(request.body);
		const token = requiredString(body.approvalToken ?? body.token, "approvalToken");
		const approval = await database.query<{ id: string; token_signature: string; expires_at: Date; status: string }>(
			"SELECT id, token_signature, expires_at, status FROM agent_approvals WHERE action_id = $1 AND session_id = $2 AND user_id = $3",
			[actionId, sessionId, userId],
		);
		const record = approval.rows[0];
		if (
			!record ||
			record.status !== "pending" ||
			record.expires_at <= new Date() ||
			!verifyToken(config, token, record.token_signature)
		) {
			throw new ApiError(400, "CONFIRMATION_REQUIRED", "确认令牌无效或已过期");
		}
		const accepted = body.accept === true;
		await database.query("UPDATE agent_approvals SET status = $1, consumed_at = now() WHERE id = $2", [
			accepted ? "consumed" : "rejected",
			record.id,
		]);
		await database.query("UPDATE agent_actions SET status = $1 WHERE id = $2", [
			accepted ? "approved" : "rejected",
			actionId,
		]);
		return { ok: true, actionId, accepted, status: accepted ? "approved" : "rejected" };
	});

	registerSkillRoutes(app, database);
	registerMemoryRoutes(app, database);
	registerFragmentRoutes(app, database);
	registerReviewRoutes(app, database);
	registerDramaRoutes(app, dramaState, config);
	registerInternalRoutes(app, database, config);
	return app;
}

function registerSkillRoutes(app: FastifyInstance, database: SqlExecutor): void {
	app.get("/api/v1/skills", async (request) => {
		const userId = requireUserId(request);
		await ensureBuiltinSkills(database);
		const query = request.query as { keyword?: string; category?: string };
		const rows = await database.query<SkillRow>(
			`SELECT id, owner_id, name, description, instructions, source, category, version, enabled, created_at, updated_at
			 FROM skills WHERE (owner_id = $1 OR owner_id = 0)
			 AND ($2::text IS NULL OR name ILIKE '%' || $2 || '%' OR description ILIKE '%' || $2 || '%')
			 AND ($3::text IS NULL OR $3 IN ('all', '全部') OR category = $3) ORDER BY owner_id DESC, name`,
			[userId, optionalString(query.keyword), optionalString(query.category)],
		);
		return { items: rows.rows.map(skillView) };
	});

	app.get("/api/v1/skills/:skillId", async (request) => {
		const skill = await requireSkill(database, requireUserId(request), routeId(request, "skillId"));
		return skillView(skill);
	});

	app.post("/api/v1/skills", async (request, reply) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const id = nextId();
		await database.query(
			`INSERT INTO skills (id, owner_id, name, description, instructions, source, category)
			 VALUES ($1, $2, $3, $4, $5, 'manual', $6)`,
			[
				id,
				userId,
				requiredString(body.name, "name"),
				optionalString(body.description),
				requiredString(body.instructions, "instructions"),
				optionalString(body.category) ?? "general",
			],
		);
		return await reply.status(201).send(skillView(await requireSkill(database, userId, id)));
	});

	app.post("/api/v1/skills/upload", async (request, reply) => {
		const userId = requireUserId(request);
		const file = await request.file();
		if (!file || (!file.filename.endsWith(".md") && !file.filename.endsWith(".markdown"))) {
			throw new ApiError(400, "INVALID_INPUT", "仅支持 .md 文件");
		}
		const instructions = (await file.toBuffer()).toString("utf8");
		if (Buffer.byteLength(instructions) > 512 * 1024) throw new ApiError(400, "INVALID_INPUT", "文件超过 512KB");
		const id = nextId();
		await database.query(
			`INSERT INTO skills (id, owner_id, name, description, instructions, source, category)
			 VALUES ($1, $2, $3, '上传的 Skill 文件', $4, 'upload', 'general')`,
			[id, userId, file.filename.replace(/\.(md|markdown)$/i, "").slice(0, 64) || "上传 Skill", instructions],
		);
		return await reply.status(201).send(skillView(await requireSkill(database, userId, id)));
	});

	app.put("/api/v1/skills/:skillId", async (request) => {
		const userId = requireUserId(request);
		const skillId = routeId(request, "skillId");
		const body = recordBody(request.body);
		const skill = await requireSkill(database, userId, skillId);
		if (skill.owner_id === "0" || skill.source === "builtin")
			throw new ApiError(403, "PERMISSION_DENIED", "内置 Skill 不可编辑内容");
		await database.query(
			`UPDATE skills SET name = COALESCE($1, name), description = COALESCE($2, description), instructions = COALESCE($3, instructions),
			 category = COALESCE($4, category), enabled = COALESCE($5, enabled),
			 version = version + CASE WHEN $3::text IS NULL THEN 0 ELSE 1 END, updated_at = now() WHERE id = $6`,
			[
				optionalString(body.name),
				optionalString(body.description),
				optionalString(body.instructions),
				optionalString(body.category),
				optionalBoolean(body.enabled),
				skillId,
			],
		);
		return skillView(await requireSkill(database, userId, skillId));
	});

	app.delete("/api/v1/skills/:skillId", async (request) => {
		const userId = requireUserId(request);
		const skill = await requireSkill(database, userId, routeId(request, "skillId"));
		if (skill.owner_id === "0" || skill.source === "builtin")
			throw new ApiError(403, "PERMISSION_DENIED", "内置 Skill 不可删除");
		await database.query("DELETE FROM skills WHERE id = $1", [skill.id]);
		return { status: "ok" };
	});
}

function registerMemoryRoutes(app: FastifyInstance, database: SqlExecutor): void {
	app.get("/api/v1/memories", async (request) => {
		const rows = await database.query<MemoryRow>(
			`SELECT id, content, memory_type, created_at FROM user_memories
			 WHERE user_id = $1 AND scope = 'long_term' AND deleted = false AND (expires_at IS NULL OR expires_at > now())
			 ORDER BY created_at DESC`,
			[requireUserId(request)],
		);
		return {
			items: rows.rows.map((memory) => ({
				id: memory.id,
				content: memory.content,
				memoryType: memory.memory_type,
				createdAt: memory.created_at.toISOString(),
			})),
		};
	});

	app.post("/api/v1/memories", async (request, reply) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const id = nextId();
		const content = requiredString(body.content, "content");
		await database.query(
			"INSERT INTO user_memories (id, user_id, content, memory_type, scope) VALUES ($1, $2, $3, $4, 'long_term')",
			[id, userId, content, optionalString(body.memoryType) ?? "preference"],
		);
		return await reply.status(201).send({ id, content });
	});

	app.delete("/api/v1/memories/:memoryId", async (request) => {
		const result = await database.query<{ id: string }>(
			"UPDATE user_memories SET deleted = true WHERE id = $1 AND user_id = $2 AND deleted = false RETURNING id",
			[routeId(request, "memoryId"), requireUserId(request)],
		);
		if (!result.rows[0]) throw new ApiError(404, "NOT_FOUND", "记忆不存在");
		return { status: "ok" };
	});
}

function registerFragmentRoutes(app: FastifyInstance, database: SqlExecutor): void {
	app.post("/api/v1/agent/sessions/:sessionId/fragments", async (request, reply) => {
		const userId = requireUserId(request);
		const session = await requireSession(database, userId, routeId(request, "sessionId"));
		const body = recordBody(request.body);
		const messages = await database.query<MessageRow>(
			"SELECT id, role, msg_type, content, meta, created_at FROM agent_messages WHERE session_id = $1 ORDER BY id",
			[session.id],
		);
		const id = nextId();
		await database.query(
			"INSERT INTO session_fragments (id, owner_id, title, content, canvas_id) VALUES ($1, $2, $3, $4::jsonb, $5)",
			[
				id,
				userId,
				optionalString(body.title) ?? session.title,
				JSON.stringify(messages.rows.map((message) => ({ role: message.role, content: message.content }))),
				session.canvas_id,
			],
		);
		return await reply.status(201).send({ fragmentId: id });
	});

	app.get("/api/v1/agent/fragments", async (request) => {
		const rows = await database.query<FragmentRow>(
			"SELECT id, title, canvas_id, content, created_at FROM session_fragments WHERE owner_id = $1 ORDER BY id DESC",
			[requireUserId(request)],
		);
		return {
			items: rows.rows.map((fragment) => ({
				id: fragment.id,
				title: fragment.title,
				canvasId: fragment.canvas_id,
				createdAt: fragment.created_at.toISOString(),
			})),
		};
	});

	app.post("/api/v1/agent/fragments/:fragmentId/import", async (request, reply) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const fragments = await database.query<FragmentRow>(
			"SELECT id, title, canvas_id, content, created_at FROM session_fragments WHERE id = $1 AND owner_id = $2",
			[routeId(request, "fragmentId"), userId],
		);
		const fragment = fragments.rows[0];
		if (!fragment) throw new ApiError(404, "NOT_FOUND", "片段不存在");
		const sessionId = nextId();
		const canvasId = optionalId(body.canvasId) ?? fragment.canvas_id;
		await database.query(
			"INSERT INTO agent_sessions (id, user_id, canvas_id, title, model_usage) VALUES ($1, $2, $3, $4, '{}'::jsonb)",
			[sessionId, userId, canvasId, fragment.title ?? "新对话"],
		);
		if (Array.isArray(fragment.content)) {
			for (const item of fragment.content) {
				if (
					typeof item === "object" &&
					item !== null &&
					"role" in item &&
					"content" in item &&
					typeof item.role === "string" &&
					typeof item.content === "string"
				) {
					if (item.role === "user" || item.role === "assistant" || item.role === "system")
						await addMessage(database, sessionId, item.role, item.content, {});
				}
			}
		}
		return await reply.status(201).send({ sessionId });
	});
}

function registerReviewRoutes(app: FastifyInstance, database: SqlExecutor): void {
	app.post("/api/v1/render-reviews", async (request, reply) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const id = nextId();
		await database.query(
			`INSERT INTO render_reviews (id, canvas_id, user_id, target_node_id, target_kind, scores, failures, recommended_action, evidence, retry_count, status)
			 VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::jsonb, $10, $11)`,
			[
				id,
				requiredId(body.canvasId, "canvasId"),
				userId,
				requiredId(body.targetNodeId, "targetNodeId"),
				optionalString(body.targetKind) ?? "clip",
				JSON.stringify(objectOrEmpty(body.scores)),
				JSON.stringify(arrayOrEmpty(body.failures)),
				optionalString(body.recommendedAction),
				JSON.stringify(objectOrEmpty(body.evidence)),
				optionalInteger(body.retryCount) ?? 0,
				optionalString(body.status) ?? "pending",
			],
		);
		return await reply.status(201).send({ id });
	});

	app.get("/api/v1/render-reviews", async (request) => {
		const userId = requireUserId(request);
		const query = request.query as { canvasId?: string; targetNodeId?: string };
		const rows = await database.query<QueryResultRow>(
			"SELECT * FROM render_reviews WHERE user_id = $1 AND canvas_id = $2 AND ($3::bigint IS NULL OR target_node_id = $3::bigint) ORDER BY created_at DESC",
			[userId, requiredId(query.canvasId, "canvasId"), optionalId(query.targetNodeId)],
		);
		return { items: rows.rows };
	});
}

function registerDramaRoutes(app: FastifyInstance, store: PgDramaStateStore, config: ServiceConfig): void {
	const gateway = new ToolGateway(config);
	app.post("/api/v1/drama/series", async (request, reply) => {
		requireUserId(request);
		const body = recordBody(request.body);
		const series: DramaSeries = {
			id: optionalString(body.id) ?? randomUUID(),
			canvasId: requiredId(body.canvasId, "canvasId"),
			activeCanonRevision: optionalInteger(body.activeCanonRevision) ?? 1,
			format: STANDARD_VERTICAL_SHORT_DRAMA_FORMAT,
		};
		await store.createSeries(series);
		return await reply.status(201).send(series);
	});

	app.post("/api/v1/drama/series/:seriesId/characters", async (request, reply) => {
		requireUserId(request);
		const body = recordBody(request.body);
		const character: CharacterProfile = {
			id: optionalString(body.id) ?? randomUUID(),
			seriesId: routeId(request, "seriesId"),
			name: requiredString(body.name, "name"),
			identityAnchors: stringArray(body.identityAnchors),
			activeLookRevision: optionalInteger(body.activeLookRevision) ?? 1,
			voiceId: requiredString(body.voiceId, "voiceId"),
		};
		await store.createCharacter(character);
		return await reply.status(201).send(character);
	});

	app.post("/api/v1/drama/characters/:characterId/reference-packs", async (request, reply) => {
		requireUserId(request);
		const body = recordBody(request.body);
		const pack: CharacterReferencePack = {
			id: optionalString(body.id) ?? randomUUID(),
			characterId: routeId(request, "characterId"),
			lookRevision: requiredInteger(body.lookRevision, "lookRevision"),
			status: referenceStatus(body.status),
			frontAssetId: requiredString(body.frontAssetId, "frontAssetId"),
			sideAssetId: requiredString(body.sideAssetId, "sideAssetId"),
			backAssetId: requiredString(body.backAssetId, "backAssetId"),
			expressionAssetIds: stringArray(body.expressionAssetIds),
		};
		await store.addReferencePack(pack);
		return await reply.status(201).send(pack);
	});

	app.post("/api/v1/drama/series/:seriesId/shots", async (request, reply) => {
		requireUserId(request);
		const body = recordBody(request.body);
		const shot: ShotSpec = {
			id: optionalString(body.id) ?? randomUUID(),
			seriesId: routeId(request, "seriesId"),
			episodeNo: requiredInteger(body.episodeNo, "episodeNo"),
			shotNo: requiredInteger(body.shotNo, "shotNo"),
			durationSeconds: requiredInteger(body.durationSeconds, "durationSeconds"),
			characterBindings: bindings(body.characterBindings),
			promptRevision: optionalInteger(body.promptRevision) ?? 1,
		};
		await store.createShot(shot);
		return await reply.status(201).send(shot);
	});

	app.post("/api/v1/drama/shots/:shotId/keyframe-node", async (request) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const draft = await store.prepareKeyframeNode(routeId(request, "shotId"));
		const canvasNode = await gateway.createCanvasNode(userId, requiredId(body.canvasId, "canvasId"), {
			type: "image",
			creativeType: "keyframe",
			prompt: requiredString(body.prompt, "prompt"),
			params: {
				shotId: draft.shotId,
				referencePackIds: draft.referencePackIds,
				referenceAssetIds: draft.referenceAssetIds,
				aspectRatio: "9:16",
				model: optionalString(body.model),
			},
		});
		return { ...draft, canvasNodeId: canvasNode.id };
	});
	app.post("/api/v1/drama/shots/:shotId/keyframes", async (request, reply) => {
		requireUserId(request);
		const body = recordBody(request.body);
		const render: KeyframeRender = {
			id: optionalString(body.id) ?? randomUUID(),
			shotId: routeId(request, "shotId"),
			status: keyframeStatus(body.status),
			referencePackIds: stringArray(body.referencePackIds),
		};
		await store.recordKeyframe(render);
		return await reply.status(201).send(render);
	});
	app.post("/api/v1/drama/shots/:shotId/video-node", async (request) => {
		const userId = requireUserId(request);
		const body = recordBody(request.body);
		const draft = await store.prepareVideoNode(routeId(request, "shotId"));
		const canvasNode = await gateway.createCanvasNode(userId, requiredId(body.canvasId, "canvasId"), {
			type: "video",
			creativeType: "clip",
			prompt: requiredString(body.prompt, "prompt"),
			params: {
				shotId: draft.shotId,
				keyframeRenderId: draft.keyframeRenderId,
				referencePackIds: draft.referencePackIds,
				aspectRatio: "9:16",
				model: optionalString(body.model),
			},
		});
		return { ...draft, canvasNodeId: canvasNode.id };
	});
	app.post("/api/v1/drama/lineages", async (request, reply) => {
		requireUserId(request);
		const body = recordBody(request.body);
		const lineage: RenderLineage = {
			id: optionalString(body.id) ?? randomUUID(),
			shotId: requiredString(body.shotId, "shotId"),
			keyframeRenderId: requiredString(body.keyframeRenderId, "keyframeRenderId"),
			status: lineageStatus(body.status),
		};
		await store.recordLineage(lineage);
		return await reply.status(201).send(lineage);
	});
	app.post("/api/v1/drama/characters/:characterId/stale-lineages", async (request) => {
		requireUserId(request);
		return { lineageIds: await store.markLineagesStaleForCharacter(routeId(request, "characterId")) };
	});
}

function registerInternalRoutes(app: FastifyInstance, database: SqlExecutor, config: ServiceConfig): void {
	app.post("/internal/agent/resume", async (request) => {
		if (config.internalServiceToken) {
			const supplied = request.headers["x-internal-service-token"];
			if (typeof supplied !== "string" || !constantTimeMatch(supplied, config.internalServiceToken))
				throw new ApiError(403, "PERMISSION_DENIED", "内部服务鉴权失败");
		}
		const body = recordBody(request.body);
		const sessionId = requiredId(body.sessionId, "sessionId");
		const taskId = requiredString(body.taskId, "taskId");
		const status = requiredString(body.status, "status");
		const result = await database.query<{ id: string }>(
			`INSERT INTO agent_wakeup_notices (id, session_id, task_id, terminal_status, canvas_id, node_id, user_id, payload)
			 VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
			 ON CONFLICT (session_id, task_id, terminal_status) DO NOTHING RETURNING id`,
			[
				nextId(),
				sessionId,
				taskId,
				status,
				optionalId(body.canvasId),
				optionalId(body.nodeId),
				optionalId(body.userId),
				JSON.stringify(objectOrEmpty(body)),
			],
		);
		return { ok: true, accepted: Boolean(result.rows[0]) };
	});
}

function requireUserId(request: FastifyRequest): string {
	const value = request.headers["x-user-id"];
	if (typeof value !== "string" || !/^\d+$/.test(value) || value === "0")
		throw new ApiError(401, "PERMISSION_DENIED", "未登录");
	return value;
}

function recordBody(value: unknown): Record<string, unknown> {
	if (typeof value !== "object" || value === null || Array.isArray(value))
		throw new ApiError(400, "INVALID_INPUT", "请求体必须是对象");
	return value as Record<string, unknown>;
}

function routeId(request: FastifyRequest, key: string): string {
	const params = request.params as Record<string, string | undefined>;
	return requiredId(params[key], key);
}

function optionalId(value: unknown): string | undefined {
	if (typeof value !== "string" && typeof value !== "number") return undefined;
	const normalized = String(value).trim();
	return /^\d+$/.test(normalized) && normalized !== "0" ? normalized : undefined;
}

function requiredId(value: unknown, field: string): string {
	return optionalId(value) ?? fail(`缺少或非法 ${field}`);
}

function requiredString(value: unknown, field: string): string {
	return typeof value === "string" && value.trim() ? value.trim() : fail(`缺少或非法 ${field}`);
}

function optionalString(value: unknown): string | undefined {
	return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function optionalInteger(value: unknown): number | undefined {
	return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function requiredInteger(value: unknown, field: string): number {
	return optionalInteger(value) ?? fail(`缺少或非法 ${field}`);
}

function optionalBoolean(value: unknown): boolean | undefined {
	return typeof value === "boolean" ? value : undefined;
}

function stringArray(value: unknown): string[] {
	if (!Array.isArray(value) || !value.every((item) => typeof item === "string" && item.trim()))
		throw new ApiError(400, "INVALID_INPUT", "字段必须是非空字符串数组");
	return value.map((item) => item.trim());
}

function uniqueStrings(values: readonly string[]): string[] {
	return [...new Set(values)];
}

function bindings(value: unknown): ShotSpec["characterBindings"] {
	if (!Array.isArray(value)) throw new ApiError(400, "INVALID_INPUT", "characterBindings 必须是数组");
	return value.map((item) => {
		if (typeof item !== "object" || item === null || Array.isArray(item))
			throw new ApiError(400, "INVALID_INPUT", "characterBindings 格式无效");
		const binding = item as Record<string, unknown>;
		return {
			characterId: requiredString(binding.characterId, "characterId"),
			lookRevision: requiredInteger(binding.lookRevision, "lookRevision"),
		};
	});
}

function referenceStatus(value: unknown): CharacterReferencePack["status"] {
	if (value === "draft" || value === "approved" || value === "retired") return value;
	throw new ApiError(400, "INVALID_INPUT", "status 无效");
}

function keyframeStatus(value: unknown): KeyframeRender["status"] {
	if (value === "draft" || value === "accepted" || value === "rejected" || value === "stale") return value;
	throw new ApiError(400, "INVALID_INPUT", "status 无效");
}

function lineageStatus(value: unknown): RenderLineage["status"] {
	if (value === "draft" || value === "ready_for_video" || value === "submitted" || value === "stale") return value;
	throw new ApiError(400, "INVALID_INPUT", "status 无效");
}

function objectOrEmpty(value: unknown): Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

function arrayOrEmpty(value: unknown): unknown[] {
	return Array.isArray(value) ? value : [];
}

function sessionView(session: SessionRow): Record<string, unknown> {
	return {
		sessionId: session.id,
		title: session.title,
		canvasId: session.canvas_id,
		updatedAt: session.updated_at.toISOString(),
	};
}

function skillView(skill: SkillRow): Record<string, unknown> {
	return {
		id: skill.id,
		name: skill.name,
		description: skill.description,
		instructions: skill.instructions,
		source: skill.source,
		category: skill.category,
		version: skill.version,
		enabled: skill.enabled,
		ownerId: skill.owner_id,
		createdAt: skill.created_at.toISOString(),
		updatedAt: skill.updated_at.toISOString(),
	};
}

async function requireSession(database: SqlExecutor, userId: string, sessionId: string): Promise<SessionRow> {
	const result = await database.query<SessionRow>(
		"SELECT id, title, canvas_id, status, token_used_total, points_used_total, model_usage, updated_at FROM agent_sessions WHERE id = $1 AND user_id = $2",
		[sessionId, userId],
	);
	if (!result.rows[0]) throw new ApiError(404, "NOT_FOUND", "会话不存在");
	return result.rows[0];
}

async function readHistory(database: SqlExecutor, sessionId: string): Promise<StoredAgentMessage[]> {
	const result = await database.query<MessageRow>(
		"SELECT id, role, msg_type, content, meta, created_at FROM agent_messages WHERE session_id = $1 ORDER BY id DESC LIMIT 48",
		[sessionId],
	);
	return result.rows
		.reverse()
		.map((message) => ({
			role: message.role,
			content: message.content,
			meta: objectOrEmpty(message.meta),
			createdAt: message.created_at,
		}));
}

async function addMessage(
	database: SqlExecutor,
	sessionId: string,
	role: "user" | "assistant" | "system",
	content: string,
	meta: Record<string, unknown>,
): Promise<void> {
	await database.query(
		"INSERT INTO agent_messages (id, session_id, role, msg_type, content, meta) VALUES ($1, $2, $3, 'text', $4, $5::jsonb)",
		[nextId(), sessionId, role, content, JSON.stringify(meta)],
	);
}

async function resolveSkillContext(
	database: SqlExecutor,
	userId: string,
	sessionId: string,
): Promise<AgentSkillContext> {
	await ensureBuiltinSkills(database);
	const session = await database.query<{ skill_snapshot: unknown; loaded_skill_ids: unknown }>(
		"SELECT skill_snapshot, loaded_skill_ids FROM agent_sessions WHERE id = $1 AND user_id = $2",
		[sessionId, userId],
	);
	const snapshotIds = stringArrayOrEmpty(session.rows[0]?.skill_snapshot);
	const loadedSkillIds = stringArrayOrEmpty(session.rows[0]?.loaded_skill_ids);
	const rows = await database.query<SkillRow>(
		`SELECT id, owner_id, name, description, instructions, source, category, version, enabled, created_at, updated_at
		 FROM skills WHERE enabled = true AND (owner_id = 0 OR owner_id = $1)`,
		[userId],
	);
	const selected = rows.rows.filter((skill) => skill.source === "builtin" || snapshotIds.includes(skill.id));
	const resources = selected.map((skill) => {
		const system = SYSTEM_SKILLS.find((candidate) => candidate.name === skill.name);
		return {
			id: skill.id,
			key: system?.key ?? `user-${skill.id}`,
			name: skill.name,
			instructions: skill.instructions,
			description: skill.description ?? "用户配置的创作方法论；仅在适用当前任务时加载。",
			kind: system?.kind ?? "dynamic",
		};
	});
	return {
		indexLines: resources.map((skill) => skillIndexLine(skill)),
		skills: resources,
		loadedSkillIds,
		onLoad: async (skill) => {
			if (loadedSkillIds.includes(skill.id)) return;
			await database.query(
				"UPDATE agent_sessions SET loaded_skill_ids = loaded_skill_ids || to_jsonb($1::text), updated_at = now() WHERE id = $2",
				[skill.id, sessionId],
			);
		},
	};
}

function stringArrayOrEmpty(value: unknown): string[] {
	return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : [];
}

async function ensureBuiltinSkills(database: SqlExecutor): Promise<void> {
	for (const skill of SYSTEM_SKILLS) {
		await database.query(
			`INSERT INTO skills (id, owner_id, name, description, instructions, source, category)
			 SELECT $1, 0, $2, $3, $4, $5, $6
			 WHERE NOT EXISTS (SELECT 1 FROM skills WHERE owner_id = 0 AND source = $5 AND name = $2)`,
			[
				nextId(),
				skill.name,
				skill.description,
				skill.instructions,
				skill.kind === "builtin-core" ? "builtin" : "system_dynamic",
				skill.category,
			],
		);
	}
}

async function requireSkill(database: SqlExecutor, userId: string, skillId: string): Promise<SkillRow> {
	const result = await database.query<SkillRow>(
		`SELECT id, owner_id, name, description, instructions, source, category, version, enabled, created_at, updated_at
		 FROM skills WHERE id = $1 AND (owner_id = $2 OR owner_id = 0)`,
		[skillId, userId],
	);
	if (!result.rows[0]) throw new ApiError(404, "NOT_FOUND", "Skill 不存在");
	return result.rows[0];
}

function sendSse(reply: FastifyReply, events: readonly AgentTurnEvent[]): FastifyReply {
	const body = events.map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join("");
	return reply
		.type("text/event-stream")
		.header("Cache-Control", "no-cache")
		.header("X-Accel-Buffering", "no")
		.send(body);
}

function verifyToken(config: ServiceConfig, token: string, signature: string): boolean {
	if (!config.confirmSigningSecret) return false;
	const expected = createHmac("sha256", config.confirmSigningSecret).update(token).digest("hex");
	return constantTimeMatch(expected, signature);
}

function constantTimeMatch(left: string, right: string): boolean {
	const first = Buffer.from(left);
	const second = Buffer.from(right);
	return first.length === second.length && timingSafeEqual(first, second);
}

function fail(message: string): never {
	throw new ApiError(400, "INVALID_INPUT", message);
}

class ApiError extends Error {
	readonly statusCode: number;
	readonly code: string;

	constructor(statusCode: number, code: string, message: string) {
		super(message);
		this.name = "ApiError";
		this.statusCode = statusCode;
		this.code = code;
	}
}

function isStatusError(error: unknown): error is { statusCode: number; message: string } {
	return (
		typeof error === "object" &&
		error !== null &&
		"statusCode" in error &&
		typeof error.statusCode === "number" &&
		"message" in error &&
		typeof error.message === "string"
	);
}
