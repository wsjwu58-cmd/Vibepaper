import type { AgentEvent, AgentMessage } from "@earendil-works/pi-agent-core";
import type { AssistantMessage, Model } from "@earendil-works/pi-ai";
import { streamSimple } from "@earendil-works/pi-ai/compat";

import type { ServiceConfig } from "../config.ts";
import type { DramaStateStore } from "../domain/drama-state.ts";
import { createDramaAgent } from "../pi/drama-agent.ts";
import { createLoadSkillTool, type LoadedSkillResource } from "../tools/skill-tools.ts";
import {
	composeUserContent,
	nodeReferencesFromMeta,
	type NodeReferenceSnapshot,
} from "./node-reference-context.ts";

export interface StoredAgentMessage {
	role: "user" | "assistant" | "system";
	content: string;
	meta: Record<string, unknown>;
	createdAt: Date;
}

export interface AgentTurnEvent {
	type: "thinking" | "assistant_message" | "tool" | "usage" | "error";
	content?: string;
	toolName?: string;
	details?: unknown;
	totalTokens?: number;
}

export interface AgentSkillContext {
	indexLines: readonly string[];
	skills: readonly LoadedSkillResource[];
	loadedSkillIds: readonly string[];
	onLoad(skill: LoadedSkillResource): Promise<void>;
}

export function agnesModel(config: ServiceConfig): Model<"openai-completions"> {
	return {
		id: config.llmModel,
		name: config.llmModel,
		api: "openai-completions",
		provider: "agnes",
		baseUrl: config.llmBaseUrl,
		reasoning: false,
		input: ["text"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 128000,
		maxTokens: 8192,
	};
}

export async function runDramaTurn(
	config: ServiceConfig,
	store: DramaStateStore,
	sessionId: string,
	history: readonly StoredAgentMessage[],
	content: string,
	skillContext: AgentSkillContext,
	nodeReferences: readonly NodeReferenceSnapshot[] = [],
): Promise<{ events: AgentTurnEvent[]; assistantText: string; totalTokens: number }> {
	if (!config.llmApiKey) {
		throw new AgentRuntimeError("MODEL_UNAVAILABLE", "未配置 VIBEPAPER_LLM_API_KEY 或 VIBEPAPER_AGNES_API_KEY");
	}
	const initialMessages: AgentMessage[] = [];
	for (const message of history.slice(-24)) {
		if (message.role === "user") {
			initialMessages.push({
				role: "user",
				content: [{ type: "text", text: composeUserContent(message.content, nodeReferencesFromMeta(message.meta)) }],
				timestamp: message.createdAt.getTime(),
			});
		}
		if (message.role === "assistant") {
			const assistant: AssistantMessage = {
				role: "assistant",
				content: [{ type: "text", text: message.content }],
				api: "openai-completions",
				provider: "agnes",
				model: config.llmModel,
				usage: {
					input: 0,
					output: 0,
					cacheRead: 0,
					cacheWrite: 0,
					totalTokens: 0,
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
				},
				stopReason: "stop",
				timestamp: message.createdAt.getTime(),
			};
			initialMessages.push(assistant);
		}
	}
	const agent = createDramaAgent(store, {
		initialState: { model: agnesModel(config), messages: initialMessages },
		streamFn: streamSimple,
		sessionId,
		getApiKey: async (provider) => (provider === "agnes" ? config.llmApiKey : undefined),
		systemPromptSuffix:
			skillContext.indexLines.length > 0
				? `可用 Skill 索引（正文未预载）：\n${skillContext.indexLines.join("\n")}`
				: undefined,
		extraTools: createLoadSkillTool(skillContext.skills, skillContext.loadedSkillIds, skillContext.onLoad),
	});
	const events: AgentTurnEvent[] = [];
	let assistantText = "";
	let totalTokens = 0;
	agent.subscribe((event) => {
		captureEvent(
			event,
			events,
			(text) => {
				assistantText = text;
			},
			(tokens) => {
				totalTokens = tokens;
			},
		);
	});
	await agent.prompt(composeUserContent(content, nodeReferences));
	return { events, assistantText, totalTokens };
}

function captureEvent(
	event: AgentEvent,
	events: AgentTurnEvent[],
	setAssistantText: (text: string) => void,
	setTotalTokens: (tokens: number) => void,
): void {
	if (event.type === "message_update" && event.message.role === "assistant") {
		const text = contentText(event.message);
		if (text) events.push({ type: "assistant_message", content: text });
		return;
	}
	if (event.type === "message_end" && event.message.role === "assistant") {
		const text = contentText(event.message);
		setAssistantText(text);
		if (text) events.push({ type: "assistant_message", content: text });
		const usage = event.message.usage;
		if (usage) {
			setTotalTokens(usage.totalTokens);
			events.push({ type: "usage", totalTokens: usage.totalTokens });
		}
		return;
	}
	if (event.type === "tool_execution_end") {
		events.push({ type: "tool", toolName: event.toolName, details: event.result });
	}
}

function contentText(message: AgentMessage): string {
	if (message.role !== "assistant" && message.role !== "user") return "";
	if (typeof message.content === "string") return message.content;
	return message.content
		.filter((item) => item.type === "text")
		.map((item) => item.text)
		.join("");
}

export class AgentRuntimeError extends Error {
	readonly code: string;

	constructor(code: string, message: string) {
		super(message);
		this.name = "AgentRuntimeError";
		this.code = code;
	}
}
