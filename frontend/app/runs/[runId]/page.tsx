import { ExecutionWorkspace } from "@/components/execution-workspace";

export default async function RunPage({ params, searchParams }: { params: Promise<{ runId: string }>; searchParams: Promise<{ compare?: string }> }) {
  const { runId } = await params;
  const { compare } = await searchParams;
  return <ExecutionWorkspace runId={runId} baselineRunId={compare} />;
}
