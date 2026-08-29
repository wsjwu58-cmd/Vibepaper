import { settings } from "./config.ts";
import { PgDatabase } from "./infrastructure/database.ts";
import { applySchema } from "./infrastructure/schema.ts";

if (!settings.databaseUrl) {
	throw new Error("VIBEPAPER_DATABASE_URL 未配置，无法执行迁移");
}

const database = new PgDatabase(settings.databaseUrl);
try {
	await applySchema(database);
} finally {
	await database.close();
}
