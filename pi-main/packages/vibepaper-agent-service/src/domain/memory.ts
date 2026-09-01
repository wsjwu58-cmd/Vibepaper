export type MemoryScope = "session" | "canvas" | "long_term" | "enterprise";

export type MemoryRecord = {
	id: string;
	userId: string;
	tenantId?: string;
	canvasId?: string;
	sessionId?: string;
	scope: MemoryScope;
	content: string;
	memoryType?: string;
	source: string;
	confidence: number;
	visibility: "user" | "enterprise";
	version: number;
	createdAt?: Date;
	expiresAt?: Date;
	deleted: boolean;
};
