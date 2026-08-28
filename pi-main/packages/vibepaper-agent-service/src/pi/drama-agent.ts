import { Agent, type AgentOptions, type AgentTool } from "@earendil-works/pi-agent-core";

import type { DramaStateStore } from "../domain/drama-state.ts";
import { createDramaTools } from "../tools/drama-tools.ts";
import { VERTICAL_SHORT_DRAMA_SYSTEM_PROMPT } from "./system-prompt.ts";

export interface CreateDramaAgentOptions {
	initialState?: AgentOptions["initialState"];
	streamFn: AgentOptions["streamFn"];
	sessionId?: string;
	getApiKey?: AgentOptions["getApiKey"];
	systemPromptSuffix?: string;
	extraTools?: AgentTool[];
}

export function createDramaAgent(store: DramaStateStore, options: CreateDramaAgentOptions): Agent {
	const tools = [...createDramaTools(store), ...(options.extraTools ?? [])];
	const allowedToolNames = new Set(tools.map((tool) => tool.name));

	return new Agent({
		initialState: {
			...options.initialState,
			systemPrompt: [VERTICAL_SHORT_DRAMA_SYSTEM_PROMPT, options.systemPromptSuffix].filter(Boolean).join("\n\n"),
			tools,
		},
		streamFn: options.streamFn,
		sessionId: options.sessionId,
		getApiKey: options.getApiKey,
		toolExecution: "sequential",
		beforeToolCall: async ({ toolCall }) => {
			if (allowedToolNames.has(toolCall.name)) return undefined;
			return {
				block: true,
				reason: "工具不在短剧 Agent 白名单中",
				terminate: true,
			};
		},
	});
}
