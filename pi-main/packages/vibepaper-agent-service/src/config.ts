export interface ServiceConfig {
	appName: string;
	port: number;
	environment: string;
	databaseUrl: string;
	redisUrl: string;
	canvasBaseUrl: string;
	assetBaseUrl: string;
	billingBaseUrl: string;
	generationBaseUrl: string;
	adminBaseUrl: string;
	identityBaseUrl: string;
	nacosAddr: string;
	nacosUsername: string;
	nacosPassword: string;
	nacosRegisterIp: string;
	llmApiKey: string;
	llmBaseUrl: string;
	llmModel: string;
	confirmTokenTtlSeconds: number;
	confirmSigningSecret: string;
	internalServiceToken: string;
}

function integerSetting(env: NodeJS.ProcessEnv, name: string, fallback: number): number {
	const parsed = Number.parseInt(env[name] ?? "", 10);
	return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeBaseUrl(value: string): string {
	const base = value.replace(/\/+$/, "");
	return base.includes("agnes-ai.com") && !base.endsWith("/v1") ? `${base}/v1` : base;
}

function normalizePostgresUrl(value: string): string {
	return value.replace(/^postgresql\+psycopg2:/, "postgres:").replace(/^postgresql:/, "postgres:");
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ServiceConfig {
	const agnesApiKey = (env.VIBEPAPER_AGNES_API_KEY ?? "").trim();
	const llmApiKey = (env.VIBEPAPER_LLM_API_KEY ?? agnesApiKey).trim() || agnesApiKey;
	const agnesBaseUrl = (env.VIBEPAPER_AGNES_BASE_URL ?? "https://apihub.agnes-ai.com/v1").trim();
	return {
		appName: (env.VIBEPAPER_APP_NAME ?? "agent-service").trim(),
		port: integerSetting(env, "VIBEPAPER_PORT", 8091),
		environment: (env.VIBEPAPER_ENVIRONMENT ?? "development").trim(),
		databaseUrl: normalizePostgresUrl((env.VIBEPAPER_DATABASE_URL ?? "").trim()),
		redisUrl: (env.VIBEPAPER_REDIS_URL ?? "").trim(),
		canvasBaseUrl: (env.VIBEPAPER_CANVAS_BASE_URL ?? "http://localhost:8082").trim(),
		assetBaseUrl: (env.VIBEPAPER_ASSET_BASE_URL ?? "http://localhost:8083").trim(),
		billingBaseUrl: (env.VIBEPAPER_BILLING_BASE_URL ?? "http://localhost:8084").trim(),
		generationBaseUrl: (env.VIBEPAPER_GENERATION_BASE_URL ?? "http://localhost:8090").trim(),
		adminBaseUrl: (env.VIBEPAPER_ADMIN_BASE_URL ?? "http://localhost:8088").trim(),
		identityBaseUrl: (env.VIBEPAPER_IDENTITY_BASE_URL ?? "http://localhost:8081").trim(),
		nacosAddr: (env.VIBEPAPER_NACOS_ADDR ?? "192.168.141.129:8848").trim(),
		nacosUsername: (env.VIBEPAPER_NACOS_USERNAME ?? "").trim(),
		nacosPassword: (env.VIBEPAPER_NACOS_PASSWORD ?? "").trim(),
		nacosRegisterIp: (env.VIBEPAPER_NACOS_REGISTER_IP ?? "").trim(),
		llmApiKey,
		llmBaseUrl: normalizeBaseUrl((env.VIBEPAPER_LLM_BASE_URL ?? agnesBaseUrl).trim() || agnesBaseUrl),
		llmModel: (env.VIBEPAPER_LLM_MODEL ?? "agnes-2.5-flash").trim(),
		confirmTokenTtlSeconds: integerSetting(env, "VIBEPAPER_CONFIRM_TOKEN_TTL_SECONDS", 300),
		confirmSigningSecret: (env.VIBEPAPER_CONFIRM_SIGNING_SECRET ?? "").trim(),
		internalServiceToken: (env.VIBEPAPER_INTERNAL_SERVICE_TOKEN ?? "").trim(),
	};
}

export const settings = loadConfig();
