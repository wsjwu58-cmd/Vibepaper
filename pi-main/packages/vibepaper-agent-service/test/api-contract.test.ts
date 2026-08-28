import type { QueryResultRow } from "pg";
import { afterEach, describe, expect, it } from "vitest";

import { createApp } from "../src/api/app.ts";
import { loadConfig } from "../src/config.ts";
import type { SqlExecutor } from "../src/infrastructure/database.ts";

type Session = {
	id: string;
	userId: string;
	canvasId: string | null;
	title: string;
	updatedAt: Date;
};

class MemoryDatabase implements SqlExecutor {
	readonly sessions: Session[] = [];

	async query<T extends QueryResultRow>(text: string, values: unknown[] = []): Promise<{ rows: T[] }> {
		if (text.startsWith("INSERT INTO agent_sessions")) {
			this.sessions.push({
				id: String(values[0]),
				userId: String(values[1]),
				canvasId: values[2] === null ? null : String(values[2]),
				title: String(values[3]),
				updatedAt: new Date(),
			});
			return { rows: [] };
		}
		if (text.includes("FROM agent_sessions WHERE user_id")) {
			const userId = String(values[0]);
			const canvasId = values[1] === null ? undefined : String(values[1]);
			return {
				rows: this.sessions
					.filter((session) => session.userId === userId && (!canvasId || session.canvasId === canvasId))
					.map((session) => ({
						id: session.id,
						title: session.title,
						canvas_id: session.canvasId,
						status: "active",
						token_used_total: 0,
						points_used_total: 0,
						model_usage: {},
						updated_at: session.updatedAt,
					})) as unknown as T[],
			};
		}
		return { rows: [] };
	}
}

const apps: ReturnType<typeof createApp>[] = [];

afterEach(async () => {
	for (const app of apps.splice(0)) await app.close();
});

describe("Pi agent service API contract", () => {
	it("keeps Agnes as the default model configuration", () => {
		const config = loadConfig({});
		expect(config.llmModel).toBe("agnes-2.5-flash");
		expect(config.llmBaseUrl).toBe("https://apihub.agnes-ai.com/v1");
	});

	it("exposes health and the legacy session response fields", async () => {
		const app = createApp({ config: loadConfig({}), database: new MemoryDatabase() });
		apps.push(app);
		const health = await app.inject({ method: "GET", url: "/health" });
		expect(health.statusCode).toBe(200);
		expect(health.json()).toMatchObject({ status: "ok", service: "agent-service", runtime: "pi-agent" });

		const created = await app.inject({
			method: "POST",
			url: "/api/v1/agent/sessions",
			headers: { "x-user-id": "101" },
			payload: { canvasId: "301", title: "短剧第一集" },
		});
		expect(created.statusCode).toBe(201);
		expect(created.json()).toMatchObject({ title: "短剧第一集", canvasId: "301" });

		const listed = await app.inject({
			method: "GET",
			url: "/api/v1/agent/sessions?canvasId=301",
			headers: { "x-user-id": "101" },
		});
		expect(listed.statusCode).toBe(200);
		expect(listed.json().items).toHaveLength(1);
		expect(listed.json().items[0]).toMatchObject({ title: "短剧第一集", canvasId: "301" });
	});
});
