import { JobWorkbench } from "../../_components/job-workbench";

export default async function JobDetailPage({ params }: Readonly<{ params: Promise<{ jobId: string }> }>) {
  const { jobId } = await params;
  return <JobWorkbench jobId={jobId} />;
}
