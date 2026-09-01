import { describe, expect, it } from "vitest";

import { migrationDirectoryFromUrl } from "../src/infrastructure/migrations.ts";

describe("migration path resolution", () => {
	it("converts a Windows file URL without duplicating the drive prefix", () => {
		const path = migrationDirectoryFromUrl(
			"file:///E:/VibePaperProject/pi-main/packages/vibepaper-agent-service/dist/server.js",
		);

		expect(path.replaceAll("\\", "/")).toBe(
			"E:/VibePaperProject/pi-main/packages/vibepaper-agent-service/migrations/",
		);
	});
});
