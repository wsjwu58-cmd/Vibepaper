import { extractProtectedFacts } from "../domain/protected-facts.ts";

export type ContextMessage = { role: string; content: string; meta?: Record<string, unknown>; sourceIndex?: number };
export type CompactedContext = {
	summary: string;
	protectedFacts: readonly string[];
	recentMessages: readonly ContextMessage[];
	tokenEstimate: number;
};

export function compactContext(messages: readonly ContextMessage[], options: { maxTokens: number }): CompactedContext {
	const protectedFacts = extractProtectedFacts(messages);
	const factTokens = estimate(protectedFacts.join("\n"));
	const summary = messages.length > 0 ? `Compacted ${messages.length} messages` : "";
	const summaryTokens = estimate(summary);
	const recentMessages: ContextMessage[] = [];
	let remaining = Math.max(0, options.maxTokens - factTokens - summaryTokens);
	for (let index = messages.length - 1; index >= 0; index -= 1) {
		const messageTokens = estimate(messages[index].content);
		if (messageTokens > remaining) continue;
		recentMessages.unshift(messages[index]);
		remaining -= messageTokens;
	}
	return {
		summary,
		protectedFacts,
		recentMessages,
		tokenEstimate: summaryTokens + factTokens + estimate(recentMessages.map((message) => message.content).join("\n")),
	};
}

function estimate(value: string): number {
	return Math.ceil(value.length / 4);
}
