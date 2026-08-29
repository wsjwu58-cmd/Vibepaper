import { describe, expect, it } from "vitest";
import { SYSTEM_SKILLS } from "../src/domain/skill-manifest.ts";
import { createLoadSkillTool } from "../src/tools/skill-tools.ts";

describe("Skill progressive disclosure", () => {
	it("extracts all workspace skills with the correct builtin/dynamic split", () => {
		expect(SYSTEM_SKILLS).toHaveLength(16);
		expect(SYSTEM_SKILLS.filter((skill) => skill.kind === "builtin-core").map((skill) => skill.key)).toEqual([
			"canvas-cookbook",
			"director-stage",
		]);
		expect(SYSTEM_SKILLS.filter((skill) => skill.kind === "dynamic")).toHaveLength(14);
	});

	it("loads the body once and returns a stable session URI", async () => {
		let loads = 0;
		const [tool] = createLoadSkillTool(
			[{ id: "42", key: "story-bible", name: "短剧故事圣经", instructions: "建立结构化事实。" }],
			[],
			async () => {
				loads += 1;
			},
		);
		const first = await tool.execute("call-1", { skill: "story-bible" });
		expect(first.content[0]).toMatchObject({ text: expect.stringContaining("skill://session/42") });
		expect(loads).toBe(1);
		const second = await tool.execute("call-2", { skill: "story-bible" });
		expect(second.details).toMatchObject({ alreadyLoaded: true });
		expect(loads).toBe(1);
	});
});
