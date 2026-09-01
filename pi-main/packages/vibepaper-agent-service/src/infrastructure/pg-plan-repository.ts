import type { QueryResultRow } from "pg";
import { CanvasDependencyCompiler } from "../application/canvas-dependency-compiler.ts";
import type { CompiledPlan } from "../application/plan-compiler.ts";
import { PlanCompileError, PlanCompiler } from "../application/plan-compiler.ts";
import type { AgentPlan, PlanStep } from "../domain/agent-plan.ts";
import type { AgentProfile } from "../domain/tool-manifest.ts";
import { nextId } from "./ids.ts";
import type { MigrationDatabase } from "./migrations.ts";

type PlanRow = QueryResultRow & {
	id: string;
	session_id: string;
	version: number;
	canvas_version: number;
	status: string;
	plan_json: unknown;
};

export class PlanRepositoryError extends Error {
	readonly code: "NOT_FOUND" | "PERMISSION_DENIED";

	constructor(code: PlanRepositoryError["code"]) {
		super(code);
		this.name = "PlanRepositoryError";
		this.code = code;
	}
}

export class PgPlanRepository {
	private readonly compiler = new PlanCompiler();
	private readonly dependencyCompiler = new CanvasDependencyCompiler();
	private readonly database: MigrationDatabase;

	constructor(database: MigrationDatabase) {
		this.database = database;
	}

	async create(input: {
		ownerId: string;
		sessionId: string;
		plan: AgentPlan;
		expectedVersion: number;
		profile: AgentProfile;
	}): Promise<CompiledPlan> {
		await this.requireSession(input.ownerId, input.sessionId);
		const compiled = this.compiler.compile(input.plan, {
			expectedVersion: input.expectedVersion,
			profile: input.profile,
		});
		await this.database.transaction(async (client) => {
			await client.query(
				`INSERT INTO agent_plans (id, session_id, version, canvas_version, status, plan_json, created_by)
				 VALUES ($1, $2, $3, $4, 'draft', $5::jsonb, $6)`,
				[
					input.plan.id,
					input.sessionId,
					input.plan.version,
					input.plan.canvasVersion,
					JSON.stringify(input.plan),
					input.ownerId,
				],
			);
			for (const step of input.plan.steps) await this.insertStep(client, input.plan.id, step);
		});
		return compiled;
	}

	async get(planId: string, ownerId: string): Promise<AgentPlan> {
		const result = await this.database.query<PlanRow>(
			`SELECT plan.id, plan.session_id, plan.version, plan.canvas_version, plan.status, plan.plan_json
			 FROM agent_plans plan JOIN agent_sessions session ON session.id = plan.session_id
			 WHERE plan.id = $1 AND session.user_id = $2`,
			[planId, ownerId],
		);
		const row = result.rows[0];
		if (!row) throw new PlanRepositoryError("NOT_FOUND");
		return toPlan(row.plan_json, row);
	}

	async readySet(planId: string, ownerId: string, profile: AgentProfile): Promise<CompiledPlan> {
		const plan = await this.get(planId, ownerId);
		return this.compiler.compile(plan, { expectedVersion: plan.version, profile });
	}

	async rerun(input: {
		planId: string;
		ownerId: string;
		stepId: string;
	}): Promise<AgentPlan & { estimatedCost: number; rerunOf: string }> {
		const current = await this.get(input.planId, input.ownerId);
		const rerun = this.dependencyCompiler.rerun(current, input.stepId);
		const next: AgentPlan = { ...rerun, id: nextId() };
		await this.database.transaction(async (client) => {
			await client.query(
				`INSERT INTO agent_plans (id, session_id, version, canvas_version, status, plan_json, created_by)
				 SELECT $1, session_id, $2, canvas_version, 'draft', $3::jsonb, $4
				 FROM agent_plans WHERE id = $5`,
				[next.id, next.version, JSON.stringify(next), input.ownerId, input.planId],
			);
			for (const step of next.steps) await this.insertStep(client, next.id, step);
		});
		return { ...next, estimatedCost: rerun.estimatedCost, rerunOf: input.planId };
	}

	private async requireSession(ownerId: string, sessionId: string): Promise<void> {
		const result = await this.database.query<{ id: string }>(
			"SELECT id FROM agent_sessions WHERE id = $1 AND user_id = $2 AND COALESCE(status, 'active') <> 'deleted'",
			[sessionId, ownerId],
		);
		if (!result.rows[0]) throw new PlanRepositoryError("PERMISSION_DENIED");
	}

	private async insertStep(
		client: { query<T extends QueryResultRow>(text: string, values?: unknown[]): Promise<{ rows: T[] }> },
		planId: string,
		step: PlanStep,
	): Promise<void> {
		await client.query(
			`INSERT INTO agent_plan_steps (id, plan_id, step_key, tool_name, depends_on, status, input_hash, estimated_cost)
			 VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)`,
			[
				nextId(),
				planId,
				step.id,
				step.tool,
				JSON.stringify(step.dependsOn),
				step.status,
				step.inputHash,
				step.estimatedCost,
			],
		);
	}
}

function toPlan(value: unknown, row: PlanRow): AgentPlan {
	if (typeof value !== "object" || value === null || Array.isArray(value))
		throw new PlanCompileError("INVALID_DEPENDENCY");
	const plan = value as Partial<AgentPlan>;
	if (typeof plan.id !== "string" || !Array.isArray(plan.steps)) throw new PlanCompileError("INVALID_DEPENDENCY");
	return {
		id: plan.id,
		sessionId: row.session_id,
		version: row.version,
		canvasVersion: row.canvas_version,
		steps: plan.steps as PlanStep[],
	};
}
