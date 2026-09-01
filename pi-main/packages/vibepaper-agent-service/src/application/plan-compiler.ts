import type { AgentPlan, PlanStep } from "../domain/agent-plan.ts";
import { type AgentProfile, getToolsForProfile } from "../domain/tool-manifest.ts";

export type PlanCompileOptions = { expectedVersion: number; profile: AgentProfile };
export type CompiledPlan = { plan: AgentPlan; readySet: readonly string[]; totalEstimatedCost: number };

export class PlanCompileError extends Error {
	readonly code: "VERSION_CONFLICT" | "TOOL_NOT_ALLOWED" | "BATCH_LIMIT_EXCEEDED" | "INVALID_DEPENDENCY";

	constructor(code: PlanCompileError["code"]) {
		super(code);
		this.name = "PlanCompileError";
		this.code = code;
	}
}

export class PlanCompiler {
	compile(plan: AgentPlan, options: PlanCompileOptions): CompiledPlan {
		if (plan.version !== options.expectedVersion) throw new PlanCompileError("VERSION_CONFLICT");
		if (plan.steps.length > 20) throw new PlanCompileError("BATCH_LIMIT_EXCEEDED");
		const allowed = new Map(getToolsForProfile(options.profile).map((entry) => [entry.name, entry]));
		const ids = new Set<string>();
		for (const step of plan.steps) {
			if (ids.has(step.id)) throw new PlanCompileError("INVALID_DEPENDENCY");
			ids.add(step.id);
			const tool = allowed.get(step.tool);
			if (!tool) throw new PlanCompileError("TOOL_NOT_ALLOWED");
			if ((step.batchSize ?? 1) > tool.maxBatch) throw new PlanCompileError("BATCH_LIMIT_EXCEEDED");
			if (step.estimatedCost < 0 || !Number.isInteger(step.estimatedCost))
				throw new PlanCompileError("INVALID_DEPENDENCY");
		}
		for (const step of plan.steps) {
			if (step.dependsOn.some((dependency) => !ids.has(dependency) || dependency === step.id))
				throw new PlanCompileError("INVALID_DEPENDENCY");
		}
		return {
			plan,
			readySet: plan.steps
				.filter(
					(step) =>
						step.status === "pending" &&
						step.dependsOn.every(
							(dependency) =>
								plan.steps.find((candidate) => candidate.id === dependency)?.status === "completed",
						),
				)
				.map((step) => step.id),
			totalEstimatedCost: plan.steps.reduce((total, step) => total + step.estimatedCost, 0),
		};
	}

	markCompleted(plan: AgentPlan, stepId: string): AgentPlan {
		if (!plan.steps.some((step) => step.id === stepId)) throw new PlanCompileError("INVALID_DEPENDENCY");
		return {
			...plan,
			version: plan.version + 1,
			steps: plan.steps.map((step) => (step.id === stepId ? { ...step, status: "completed" } : step)),
		};
	}
}

export function clonePlanStep(step: PlanStep, overrides: Partial<PlanStep> = {}): PlanStep {
	return { ...step, ...overrides, dependsOn: [...(overrides.dependsOn ?? step.dependsOn)] };
}
