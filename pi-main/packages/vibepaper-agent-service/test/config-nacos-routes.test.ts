import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { loadConfig, validateStartupConfig } from "../src/config.ts";

describe("production startup and routing contracts", () => {
	it("fails closed when production secrets and service credentials are absent", () => {
		const config = loadConfig({ VIBEPAPER_ENVIRONMENT: "production" });
		expect(() => validateStartupConfig(config)).toThrow("VIBEPAPER_INTERNAL_SERVICE_TOKEN");
	});

	it("requires valid explicit Snowflake coordinates", () => {
		const config = loadConfig({
			VIBEPAPER_ENVIRONMENT: "production",
			VIBEPAPER_INTERNAL_SERVICE_TOKEN: "internal",
			VIBEPAPER_CONFIRM_SIGNING_SECRET: "confirm",
			VIBEPAPER_NACOS_USERNAME: "nacos",
			VIBEPAPER_NACOS_PASSWORD: "nacos",
			VIBEPAPER_NACOS_REGISTER_IP: "127.0.0.1",
			VIBEPAPER_DATABASE_URL: "postgres://localhost/agent",
			VIBEPAPER_SNOWFLAKE_WORKER_ID: "4",
			VIBEPAPER_SNOWFLAKE_DATACENTER_ID: "2",
		});
		expect(() => validateStartupConfig(config)).not.toThrow();
	});

	it("routes all Agent control-plane resources and requires a Pi CI job", () => {
		const root = resolve(import.meta.dirname, "../../../../");
		const gateway = readFileSync(
			resolve(root, "vibepaper-services/vibepaper-gateway/src/main/resources/application.yml"),
			"utf8",
		);
		const ci = readFileSync(resolve(root, ".github/workflows/ci.yml"), "utf8");
		expect(gateway).toContain("/api/v1/drama/**");
		expect(gateway).toContain("/api/v1/render-reviews/**");
		expect(ci).toContain("pi-agent-service:");
	});
});
