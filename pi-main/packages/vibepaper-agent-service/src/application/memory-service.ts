import type { MemoryRecord, MemoryScope } from "../domain/memory.ts";
import { nextId } from "../infrastructure/ids.ts";

export type WriteMemoryInput = {
	userId: string;
	tenantId?: string;
	canvasId?: string;
	sessionId?: string;
	scope: MemoryScope;
	content: string;
	memoryType?: string;
	confidence: number;
	source?: string;
	visibility?: "user" | "enterprise";
	expiresAt?: Date;
	adminAuthorized?: boolean;
};

export type SearchMemoryInput = {
	userId: string;
	tenantId?: string;
	canvasId?: string;
	sessionId?: string;
	scope?: MemoryScope;
	query: string;
	topK: number;
	now?: Date;
};

export interface MemoryRepository {
	list(): readonly MemoryRecord[] | Promise<readonly MemoryRecord[]>;
	save(memory: MemoryRecord): void | Promise<void>;
	softDelete(id: string, userId: string): boolean | Promise<boolean>;
}

export class MemoryService {
	private readonly repository: MemoryRepository;

	constructor(repository: MemoryRepository) {
		this.repository = repository;
	}

	async write(input: WriteMemoryInput): Promise<MemoryRecord> {
		if (/(api[_-]?key|password|secret|token)\s*[:=]/i.test(input.content))
			throw new Error("SENSITIVE_MEMORY_REJECTED");
		if (input.scope === "enterprise" && (!input.tenantId || !input.adminAuthorized))
			throw new Error("PERMISSION_DENIED");
		if (!input.content.trim() || input.confidence < 0 || input.confidence > 1) throw new Error("INVALID_INPUT");
		const existing = (await this.repository.list()).find(
			(memory) =>
				!memory.deleted &&
				memory.userId === input.userId &&
				memory.scope === input.scope &&
				memory.tenantId === input.tenantId &&
				memory.canvasId === input.canvasId &&
				memory.sessionId === input.sessionId &&
				memory.content.trim().toLocaleLowerCase() === input.content.trim().toLocaleLowerCase(),
		);
		if (existing) return existing;
		const memory: MemoryRecord = {
			id: nextId(),
			userId: input.userId,
			tenantId: input.tenantId,
			canvasId: input.canvasId,
			sessionId: input.sessionId,
			scope: input.scope,
			content: input.content.trim(),
			memoryType: input.memoryType ?? input.scope,
			source: input.source ?? "agent",
			confidence: input.confidence,
			visibility: input.visibility ?? (input.scope === "enterprise" ? "enterprise" : "user"),
			version: 1,
			createdAt: new Date(),
			expiresAt: input.expiresAt,
			deleted: false,
		};
		await this.repository.save(memory);
		return memory;
	}

	async search(input: SearchMemoryInput): Promise<readonly MemoryRecord[]> {
		const now = input.now ?? new Date();
		const terms = input.query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
		return (await this.repository.list())
			.filter((memory) => !memory.deleted && (!memory.expiresAt || memory.expiresAt > now))
			.filter((memory) => memory.userId === input.userId)
			.filter((memory) => !input.scope || memory.scope === input.scope)
			.filter((memory) => memory.scope !== "enterprise" || memory.tenantId === input.tenantId)
			.filter((memory) => !input.canvasId || !memory.canvasId || memory.canvasId === input.canvasId)
			.filter((memory) => !input.sessionId || !memory.sessionId || memory.sessionId === input.sessionId)
			.map((memory) => ({
				memory,
				score: terms.filter((term) => memory.content.toLocaleLowerCase().includes(term)).length,
			}))
			.filter((entry) => terms.length === 0 || entry.score > 0)
			.sort((left, right) => right.score - left.score || right.memory.confidence - left.memory.confidence)
			.slice(0, Math.max(0, input.topK))
			.map((entry) => entry.memory);
	}

	async remove(id: string, userId: string): Promise<void> {
		if (!(await this.repository.softDelete(id, userId))) throw new Error("NOT_FOUND");
	}

	async export(userId: string): Promise<readonly MemoryRecord[]> {
		return (await this.repository.list()).filter((memory) => memory.userId === userId && !memory.deleted);
	}
}

export class InMemoryMemoryRepository implements MemoryRepository {
	private readonly memories: MemoryRecord[] = [];

	list(): readonly MemoryRecord[] {
		return [...this.memories];
	}
	save(memory: MemoryRecord): void {
		this.memories.push(memory);
	}
	softDelete(id: string, userId: string): boolean {
		const memory = this.memories.find(
			(candidate) => candidate.id === id && candidate.userId === userId && !candidate.deleted,
		);
		if (!memory) return false;
		memory.deleted = true;
		return true;
	}
}
