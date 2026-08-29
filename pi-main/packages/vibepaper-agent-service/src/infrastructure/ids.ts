let sequence = 0n;
const nodeId = BigInt(process.pid & 0x3ff);
const epoch = 1_704_067_200_000n;

export function nextId(): string {
	sequence = (sequence + 1n) & 0xfffn;
	const timestamp = BigInt(Date.now()) - epoch;
	return ((timestamp << 22n) | (nodeId << 12n) | sequence).toString();
}
