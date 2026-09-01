import { describe, expect, it } from "vitest";
import { CanvasDependencyCompiler } from "../src/application/canvas-dependency-compiler.ts";
import { PlanCompileError, PlanCompiler } from "../src/application/plan-compiler.ts";
import type { AgentPlan, PlanStep } from "../src/domain/agent-plan.ts";

const step = (id: string, dependsOn: string[] = [], status: PlanStep["status"] = "pending"): PlanStep => ({
	id,
	tool: "get_canvas_summary",
	dependsOn,
	status,
	inputHash: `hash-${id}`,
	estimatedCost: 0,
});

const plan: AgentPlan = {
	id: "plan-1",
	sessionId: "session-1",
	version: 1,
	canvasVersion: 7,
	steps: [step("read"), step("write", ["read"]), step("render", ["write"])],
};

describe("structured plans and dependency compiler", () => {
	it("rejects stale plan versions and only returns the current Ready Set", () => {
		const compiler = new PlanCompiler();
		const compiled = compiler.compile(plan, { expectedVersion: 1, profile: "canvas-general" });
		expect(compiled.readySet).toEqual(["read"]);
		expect(() => compiler.compile(plan, { expectedVersion: 2, profile: "canvas-general" })).toThrowError(
			new PlanCompileError("VERSION_CONFLICT"),
		);
		const completed = compiler.markCompleted(plan, "read");
		expect(compiler.compile(completed, { expectedVersion: 2, profile: "canvas-general" }).readySet).toEqual([
			"write",
		]);
	});

	it("propagates stale state through dependents and scopes local reruns", () => {
		const compiler = new CanvasDependencyCompiler();
		const impacted = compiler.impactSet(plan.steps, ["write"]);
		expect(impacted).toEqual(["write", "render"]);
		const rerun = compiler.rerun(plan, "write");
		expect(rerun.steps.find((candidate) => candidate.id === "write")?.status).toBe("pending");
		expect(rerun.steps.find((candidate) => candidate.id === "read")?.status).toBe("pending");
		expect(rerun.estimatedCost).toBe(0);
	});

	it("accepts only manifest tools and rejects oversized batches", () => {
		const compiler = new PlanCompiler();
		expect(() =>
			compiler.compile(
				{ ...plan, steps: [{ ...step("unknown"), tool: "unknown_tool" }] },
				{ expectedVersion: 1, profile: "canvas-general" },
			),
		).toThrow(new PlanCompileError("TOOL_NOT_ALLOWED"));
		const tooMany = Array.from({ length: 21 }, (_, index) => step(`step-${index}`));
		expect(() =>
			compiler.compile({ ...plan, steps: tooMany }, { expectedVersion: 1, profile: "canvas-general" }),
		).toThrow(new PlanCompileError("BATCH_LIMIT_EXCEEDED"));
	});
});
