import { describe, expect, it } from "vitest";

import { resolveEvalFiles, resolveEvidenceRoot } from "../evals/case-loader.ts";

describe("evaluation case CLI paths", () => {
	it("expands the plan's Windows wildcard from the monorepo root", async () => {
		const files = await resolveEvalFiles(
			["packages/vibepaper-agent-service/evals/cases/*.json"],
			"E:/VibePaperProject/pi-main",
		);

		expect(files).toHaveLength(16);
		expect(files.every((file) => file.endsWith(".json"))).toBe(true);
	});

	it("writes default evidence below the repository output directory", () => {
		expect(
			resolveEvidenceRoot("E:/VibePaperProject/pi-main/packages/vibepaper-agent-service", "2026-08-29").replaceAll(
				"\\",
				"/",
			),
		).toBe("E:/VibePaperProject/output/evals/2026-08-29");
	});
});
