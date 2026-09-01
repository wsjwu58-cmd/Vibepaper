import { createApp } from "./api/app.ts";
import { settings, validateStartupConfig } from "./config.ts";
import { PgDatabase } from "./infrastructure/database.ts";
import { configureIdGenerator } from "./infrastructure/ids.ts";
import { applyMigrations, migrationDirectoryFromUrl } from "./infrastructure/migrations.ts";
import { NacosRegistrar } from "./infrastructure/nacos.ts";

if (!settings.databaseUrl) {
	throw new Error("VIBEPAPER_DATABASE_URL 未配置，agent-service 无法启动");
}
validateStartupConfig(settings);

const database = new PgDatabase(settings.databaseUrl);
configureIdGenerator(settings.workerId, settings.datacenterId);
await applyMigrations(database, migrationDirectoryFromUrl(import.meta.url));
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
