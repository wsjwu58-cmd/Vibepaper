export const memorySchema = {
	type: "object",
	required: ["content"],
	properties: {
		content: { type: "string" },
		scope: { enum: ["session", "canvas", "long_term", "enterprise"] },
		visibility: { type: "string" },
	},
} as const;
