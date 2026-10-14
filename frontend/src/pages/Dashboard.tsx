import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { downloadFile } from "../api/client";
import type { Dashboard as D } from "../types";
import { Button, Card, Empty, ErrorPanel, Loading, PageHeader, Stat, StatusBadge } from "../components/ui";

export default function Dashboard() {
  const { data, error, loading } = useApi<D>("/dashboard");
  const [downloading, setDownloading] = useState(false);

  const handleDownloadMarksheet = async () => {
    try {
      setDownloading(true);
      await downloadFile("/reports/marksheet", "ADEM_Student_Marksheet.xlsx");
    } catch (err: any) {
      alert(err.message || "Failed to download marksheet.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <Loading />;
  if (error || !data) return <ErrorPanel error={error} />;
  return (
    <>
      <PageHeader
        title="Dashboard"
        actions={
          <div className="flex items-center gap-2">
            <Button variant="soft" busy={downloading} onClick={handleDownloadMarksheet}>
              Download Marksheet (.xlsx)
            </Button>
            <Link to="/exams/new">
              <Button variant="primary">Create exam</Button>
            </Link>
          </div>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <Stat label="Classes" value={data.total_classes} /><Stat label="Subjects" value={data.total_subjects} />
        <Stat label="Exams" value={data.total_exams} /><Stat label="Students" value={data.total_students} />
        <Stat label="Pending evaluations" value={data.pending_evaluations} tone={data.pending_evaluations ? "mark" : undefined} />
        <Stat label="Completed" value={data.completed_evaluations} />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section><h2 className="mb-2 font-semibold">Recent exams</h2>
          {data.recent_exams.length === 0 ? <Empty title="No exams yet" hint="Create an exam to upload its question paper." /> : (
            <Card className="divide-y divide-line">{data.recent_exams.map((e) => (
              <Link key={e.id} to={`/exams/${e.id}`} className="flex items-center justify-between p-3 hover:bg-sunken">
                <div><p className="font-medium">{e.name}</p><p className="text-xs text-mute">{e.class_name} · {e.subject_name}</p></div><StatusBadge status={e.status} />
              </Link>))}</Card>)}
        </section>
        <section><h2 className="mb-2 font-semibold">Recent evaluations</h2>
          {data.recent_evaluations.length === 0 ? <Empty title="No answer sheets yet" /> : (
            <Card className="divide-y divide-line">{data.recent_evaluations.map((e) => (
              <Link key={e.id} to={e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`} className="flex items-center justify-between p-3 hover:bg-sunken">
                <div><p className="font-medium">{e.student.name}</p><p className="text-xs text-mute">{e.exam_name}</p></div><StatusBadge status={e.status} />
              </Link>))}</Card>)}
        </section>
      </div>
    </>
  );
}
