import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { downloadFile } from "../api/client";
import type { Dashboard as D } from "../types";
import {
  Button,
  Card,
  Empty,
  ErrorPanel,
  Loading,
  Stat,
  StatusBadge,
} from "../components/ui";
import {
  IconClasses,
  IconSubjects,
  IconExam,
  IconStudents,
  IconClock,
  IconCheckCircle,
  IconDownload,
  IconPlus,
  IconChevronRight,
  IconFileText,
} from "../components/Icons";
import { useAuth } from "../context/Auth";

export default function Dashboard() {
  const { teacher } = useAuth();
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

  if (loading) return <Loading text="Loading your dashboard overview..." />;
  if (error || !data) return <ErrorPanel error={error} />;

  return (
    <div className="space-y-6">
      {/* Welcome & Overview Header */}
      <div className="ruled relative flex flex-col gap-4 overflow-hidden rounded-lg border border-line bg-surface py-7 pl-16 pr-6 shadow-card sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-mark/80">Today&rsquo;s marking</p>
          <h1 className="font-display text-3xl font-semibold text-ink">
            Welcome back{teacher?.name ? `, ${teacher.name}` : ""}
          </h1>
          <p className="text-sm text-mute">
            {data.pending_evaluations > 0 ? (
              <>
                <span className="hl font-semibold text-ink">{data.pending_evaluations} scripts</span> are waiting for your
                review.
              </>
            ) : (
              "Every script is marked. Your desk is clear."
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            variant="secondary"
            busy={downloading}
            onClick={handleDownloadMarksheet}
            icon={<IconDownload size={16} />}
          >
            Export Marksheet (.xlsx)
          </Button>
          <Link to="/exams/new">
            <Button variant="primary" icon={<IconPlus size={16} />}>
              Create Exam
            </Button>
          </Link>
        </div>
      </div>

      {/* Operational Metrics Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat
          label="Classes"
          value={data.total_classes}
          icon={<IconClasses size={20} />}
          hint="Assigned classes"
        />
        <Stat
          label="Subjects"
          value={data.total_subjects}
          icon={<IconSubjects size={20} />}
          hint="Active subjects"
        />
        <Stat
          label="Total Exams"
          value={data.total_exams}
          icon={<IconExam size={20} />}
          hint="Created assessments"
        />
        <Stat
          label="Students"
          value={data.total_students}
          icon={<IconStudents size={20} />}
          hint="Registered students"
        />
        <Stat
          label="Pending Review"
          value={data.pending_evaluations}
          tone={data.pending_evaluations > 0 ? "warn" : "mute"}
          icon={<IconClock size={20} />}
          hint={data.pending_evaluations > 0 ? "Awaiting review" : "Up to date"}
        />
        <Stat
          label="Completed"
          value={data.completed_evaluations}
          tone="ok"
          icon={<IconCheckCircle size={20} />}
          hint="Finalized evaluations"
        />
      </div>

      {/* Quick Action Shortcuts */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Link
          to="/exams/new"
          className="group relative flex items-center gap-3.5 rounded-lg border border-line bg-surface p-3.5 shadow-card transition-ui hover:-translate-y-0.5 hover:border-pen/40"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-pen/10 text-pen group-hover:bg-pen group-hover:text-surface transition-colors">
            <IconPlus size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink group-hover:text-brown transition-colors">New Examination</p>
            <p className="text-xs text-mute truncate">Setup paper, key & criteria</p>
          </div>
        </Link>

        <Link
          to="/exams"
          className="group relative flex items-center gap-3.5 rounded-lg border border-line bg-surface p-3.5 shadow-card transition-ui hover:-translate-y-0.5 hover:border-pen/40"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-ok/10 text-ok group-hover:bg-ok group-hover:text-surface transition-colors">
            <IconFileText size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink group-hover:text-brown transition-colors">Upload Answer Sheets</p>
            <p className="text-xs text-mute truncate">Add scans for reading</p>
          </div>
        </Link>

        <Link
          to="/evaluations"
          className="group relative flex items-center gap-3.5 rounded-lg border border-line bg-surface p-3.5 shadow-card transition-ui hover:-translate-y-0.5 hover:border-pen/40"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-warn/10 text-warn group-hover:bg-warn group-hover:text-surface transition-colors">
            <IconClock size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink group-hover:text-brown transition-colors">Pending Evaluations</p>
            <p className="text-xs text-mute truncate">{data.pending_evaluations} submissions to review</p>
          </div>
        </Link>

        <Link
          to="/results"
          className="group relative flex items-center gap-3.5 rounded-lg border border-line bg-surface p-3.5 shadow-card transition-ui hover:-translate-y-0.5 hover:border-pen/40"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-pen-soft text-pen group-hover:bg-pen group-hover:text-surface transition-colors">
            <IconCheckCircle size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink group-hover:text-brown transition-colors">Class Marksheets</p>
            <p className="text-xs text-mute truncate">View score distributions</p>
          </div>
        </Link>
      </div>

      {/* Recent Activity Sections */}
      <div className="grid gap-8 lg:grid-cols-2">
        {/* Recent Exams */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-xl font-semibold text-ink">Recent Exams</h2>
              <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-medium text-mute">
                {data.recent_exams.length}
              </span>
            </div>
            <Link
              to="/exams"
              className="flex items-center gap-1 text-xs font-medium text-pen hover:underline"
            >
              <span>View all</span>
              <IconChevronRight size={14} />
            </Link>
          </div>

          {data.recent_exams.length === 0 ? (
            <Empty
              title="No exams created yet"
              hint="Create your first exam to get started."
              icon={<IconExam size={24} />}
              action={
                <Link to="/exams/new">
                  <Button variant="primary" small icon={<IconPlus size={14} />}>
                    Create Exam
                  </Button>
                </Link>
              }
            />
          ) : (
            <Card className="divide-y divide-dashed divide-line overflow-hidden">
              {data.recent_exams.map((e) => (
                <Link
                  key={e.id}
                  to={`/exams/${e.id}`}
                  className="flex items-center justify-between p-4 transition-ui hover:bg-hover group"
                >
                  <div className="min-w-0 flex-1 pr-4">
                    <p className="truncate font-semibold text-sm text-ink group-hover:text-brown transition-colors">
                      {e.name}
                    </p>
                    <div className="mt-1 flex items-center gap-2 text-xs text-mute">
                      <span>{e.class_name}</span>
                      <span>•</span>
                      <span>{e.subject_name}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <StatusBadge status={e.status} />
                    <IconChevronRight size={16} className="text-mute/60 group-hover:text-brown transition-colors" />
                  </div>
                </Link>
              ))}
            </Card>
          )}
        </section>

        {/* Recent Evaluations */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-xl font-semibold text-ink">Recent Evaluations</h2>
              <span className="rounded-full bg-sunken px-2 py-0.5 text-xs font-medium text-mute">
                {data.recent_evaluations.length}
              </span>
            </div>
            <Link
              to="/evaluations"
              className="flex items-center gap-1 text-xs font-medium text-pen hover:underline"
            >
              <span>View all</span>
              <IconChevronRight size={14} />
            </Link>
          </div>

          {data.recent_evaluations.length === 0 ? (
            <Empty
              title="No answer sheets evaluated yet"
              hint="Open an existing exam to upload student answer sheets for reading."
              icon={<IconFileText size={24} />}
            />
          ) : (
            <Card className="divide-y divide-dashed divide-line overflow-hidden">
              {data.recent_evaluations.map((e) => {
                const targetLink =
                  e.status === "FINALIZED" ? `/results/${e.id}` : `/evaluations/${e.id}`;
                return (
                  <Link
                    key={e.id}
                    to={targetLink}
                    className="flex items-center justify-between p-4 transition-ui hover:bg-hover group"
                  >
                    <div className="min-w-0 flex-1 pr-4">
                      <div className="flex items-center gap-2">
                        <p className="truncate font-semibold text-sm text-ink group-hover:text-brown transition-colors">
                          {e.student.name}
                        </p>
                        <span className="rounded bg-sunken px-1.5 py-0.2 text-[11px] font-mono text-mute">
                          {e.student.roll_number}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-xs text-mute">{e.exam_name}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <StatusBadge status={e.status} />
                      <IconChevronRight size={16} className="text-mute/60 group-hover:text-brown transition-colors" />
                    </div>
                  </Link>
                );
              })}
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}
