import { VersionViewer } from "../../_components/version-viewer";

export default async function VersionDetailPage({ params }: Readonly<{ params: Promise<{ versionId: string }> }>) {
  const { versionId } = await params;
  return <VersionViewer versionId={versionId} />;
}
