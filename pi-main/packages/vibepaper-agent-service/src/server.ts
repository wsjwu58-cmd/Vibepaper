import { createApp } from "./api/app.ts";
import { settings } from "./config.ts";
import { PgDatabase } from "./infrastructure/database.ts";
import { NacosRegistrar } from "./infrastructure/nacos.ts";
import { applySchema } from "./infrastructure/schema.ts";

if (!settings.databaseUrl) {
	throw new Error("VIBEPAPER_DATABASE_URL 未配置，agent-service 无法启动");
}

const database = new PgDatabase(settings.databaseUrl);
await applySchema(database);
const app = createApp({ config: settings, database });
const nacos = new NacosRegistrar(settings, settings.port);

for (const signal of ["SIGINT", "SIGTERM"] as const) {
	process.once(signal, () => {
		void nacos.stop();
		void app.close();
		void database.close();
	});
}

await app.listen({ host: "0.0.0.0", port: settings.port });
await nacos.start();
