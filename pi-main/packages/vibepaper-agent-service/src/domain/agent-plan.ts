export type PlanStepStatus = "pending" | "running" | "completed" | "failed" | "stale";

export interface PlanStep {
	id: string;
	tool: string;
	dependsOn: readonly string[];
	status: PlanStepStatus;
	inputHash: string;
	input?: Record<string, unknown>;
	estimatedCost: number;
	batchSize?: number;
}

export interface AgentPlan {
	id: string;
	sessionId: string;
	version: number;
	canvasVersion: number;
	steps: readonly PlanStep[];
}
