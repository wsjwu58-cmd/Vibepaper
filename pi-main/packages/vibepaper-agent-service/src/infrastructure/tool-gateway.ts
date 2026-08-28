import type { ServiceConfig } from "../config.ts";

export interface CanvasNodeRequest {
	type: "image" | "video";
	creativeType: "keyframe" | "clip";
	prompt: string;
	params: Record<string, unknown>;
}

export interface CreatedCanvasNode {
	id: string;
	data: Record<string, unknown>;
}

export class ToolGateway {
	private readonly config: ServiceConfig;

	constructor(config: ServiceConfig) {
		this.config = config;
	}

	async createCanvasNode(userId: string, canvasId: string, node: CanvasNodeRequest): Promise<CreatedCanvasNode> {
		const response = await fetch(`${this.config.canvasBaseUrl}/api/v1/canvases/${canvasId}/nodes`, {
			method: "POST",
			headers: requestHeaders(userId),
			body: JSON.stringify({ ...node, x: 220, y: 180, modelRef: node.params.model }),
			signal: AbortSignal.timeout(10_000),
		});
		const data = await responseData(response);
		if (!response.ok) throw new ToolGatewayError("CANVAS_UNAVAILABLE", "创建画布节点失败", data);
		const id = objectId(data);
		if (!id) throw new ToolGatewayError("INVALID_RESPONSE", "画布服务未返回节点 ID", data);
		return { id, data: objectValue(data) };
	}

	async submitGeneration(
		userId: string,
		canvasId: string,
		nodeId: string,
		modelType: string,
		modelParams: Record<string, unknown>,
		estimatedCost: number,
		idempotencyKey: string,
	): Promise<Record<string, unknown>> {
		const response = await fetch(`${this.config.billingBaseUrl}/api/v1/tasks`, {
			method: "POST",
			headers: { ...requestHeaders(userId), "Idempotency-Key": idempotencyKey },
			body: JSON.stringify({
				userId,
				canvasId,
				nodeId,
				modelType,
				modelParams,
				estimatedCost,
				source: "agent",
			}),
			signal: AbortSignal.timeout(15_000),
		});
		const data = await responseData(response);
		if (!response.ok) throw new ToolGatewayError("GENERATION_UNAVAILABLE", "提交生成任务失败", data);
		await fetch(`${this.config.canvasBaseUrl}/api/v1/canvases/${canvasId}/nodes/${nodeId}`, {
			method: "PUT",
			headers: requestHeaders(userId),
			body: JSON.stringify({ status: "queued", execStatus: "queued", stale: false }),
			signal: AbortSignal.timeout(10_000),
		}).catch(() => undefined);
		return objectValue(data);
	}
}

function requestHeaders(userId: string): Record<string, string> {
	return {
		"Content-Type": "application/json",
		"X-User-Id": userId,
		"X-User-Role": "user",
		"X-Request-Id": crypto.randomUUID(),
	};
}

async function responseData(response: Response): Promise<unknown> {
	const text = await response.text();
	if (!text) return {};
	try {
		return JSON.parse(text) as unknown;
	} catch {
		return { raw: text.slice(0, 500) };
	}
}

function objectValue(value: unknown): Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

function objectId(value: unknown): string | undefined {
	const record = objectValue(value);
	const candidate = record.id ?? record.nodeId;
	return typeof candidate === "string" || typeof candidate === "number" ? String(candidate) : undefined;
}

export class ToolGatewayError extends Error {
	readonly code: string;
	readonly details: unknown;

	constructor(code: string, message: string, details: unknown) {
		super(message);
		this.name = "ToolGatewayError";
		this.code = code;
		this.details = details;
	}
}
