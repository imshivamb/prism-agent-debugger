export type EventStatus = "completed" | "failed" | "active";

export type ToolCall = { name: string; summary: string; status: "success" | "error" };

export type ExecutionEvent = {
  id: string;
  sequence: number;
  phase: string;
  title: string;
  timestamp: string;
  duration: string;
  status: EventStatus;
  prompt: string;
  input: string;
  output: string;
  toolCalls: ToolCall[];
  metadata: { latency: string; tokens: string; model: string };
  parentEventId?: string | null;
  insight: string;
  position: { x: number; y: number };
};
