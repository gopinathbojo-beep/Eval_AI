import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useToast } from "../components/Toast";
import { useApi } from "../hooks/useApi";
import { downloadFile } from "../api/client";
import type { Dashboard as D } from "../types";
import { Empty, ErrorPanel, Loading, StatusBadge } from "../components/ui";
import {
  IconCheckCircle,
  IconClock,
  IconDownload,
  IconExam,
    IconPlus,
  } from "../components/Icons";
import { useAuth } from "../context/Auth";

/** School Management dashboard matching the modern Eval AI layout. */
export default function Dashboard() {
  const { teacher } = useAuth();
  const { data, error, loading } = useApi<D>("/dashboard");
  const toast = useToast();
  const nav = useNavigate();
  const [downloading, setDownloading] = useState(false);

  const downloadMarksheet = async () => {
    try {
      setDownloading(true);
      await downloadFile("/reports/marksheet", "Student_Marksheet.xlsx");
      toast("Marksheet downloaded.");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Failed to download marksheet.", "mark");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) return <Loading text="Loading dashboard..." />;
  if (error || !data) return <ErrorPanel error={error} />;

  return (
    <div className="w-full">
      {/* Giant Floating White Canvas */}
      <div className="glass-canvas p-5 sm:p-7 lg:p-8 space-y-7 stagger">
        
        {/* Welcome row & Action buttons */}
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="aurora-text text-2xl sm:text-[2rem] font-bold tracking-tight">
              Welcome{teacher?.name ? `, ${teacher.name}` : ""}
            </h1>
            <p className="mt-1.5 text-sm sm:text-base font-medium text-blue-800/80">
              An overview of your school's exams and evaluated answer sheets
            </p>
          </div>
          
          <div className="flex flex-wrap items-center gap-3">
            {/* Export marksheet button */}
            <button
              type="button"
              disabled={downloading}
              onClick={downloadMarksheet}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200/90 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 hover:border-slate-300 active:scale-[0.98] transition-all cursor-pointer disabled:opacity-50"
            >
              <IconDownload size={16} className="text-slate-600" />
              <span>{downloading ? "Exporting..." : "Export marksheet"}</span>
            </button>

            {/* Create Exam button */}
            <Link
              to="/exams/new"
              className="inline-flex items-center gap-2 rounded-full aurora-fill px-6 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-500/25 active:scale-[0.98] transition-all"
            >
              <IconPlus size={16} />
              <span>Create Exam</span>
            </Link>
          </div>
        </div>

        {/* 3 Stat Cards */}
        <div className="stagger grid grid-cols-1 gap-5 sm:grid-cols-3">
          
          {/* Card 1: Total Exams */}
          <div className="lift-card group relative flex flex-col justify-between overflow-hidden rounded-3xl bg-white/80 p-5 sm:p-6 shadow-[0_8px_24px_-18px_rgba(30,64,175,0.4)]">
            <div>
              <div className="flex items-center justify-between text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Exams</span>
                </div>
                <span className="corner-icon flex h-9 w-9 items-center justify-center rounded-full bg-blue-50 text-blue-600"><IconExam size={18} /></span>
              </div>
              <p className="mt-3 text-[2rem] font-bold leading-none tracking-tight tabular-nums text-slate-900">
                {data.total_exams}
              </p>
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500">
              Active exams in workspace
            </p>
          </div>

          {/* Card 3: Pending Review */}
          <div className="lift-card group relative flex flex-col justify-between overflow-hidden rounded-3xl bg-white/80 p-5 sm:p-6 shadow-[0_8px_24px_-18px_rgba(30,64,175,0.4)]">
            <div>
              <div className="flex items-center justify-between text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pending Review</span>
                </div>
                <span className="corner-icon flex h-9 w-9 items-center justify-center rounded-full bg-amber-50 text-amber-500"><IconClock size={18} /></span>
              </div>
              <p className="mt-3 text-[2rem] font-bold leading-none tracking-tight tabular-nums text-amber-500">
                {data.pending_review}
              </p>
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500">
              {data.pending_review ? "Sheets flagged for a check" : "Nothing to review"}
            </p>
          </div>

          {/* Card 4: Evaluated Sheets */}
          <div className="lift-card group relative flex flex-col justify-between overflow-hidden rounded-3xl bg-white/80 p-5 sm:p-6 shadow-[0_8px_24px_-18px_rgba(30,64,175,0.4)]">
            <div>
              <div className="flex items-center justify-between text-slate-500">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Evaluated Sheets</span>
                </div>
                <span className="corner-icon flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-500"><IconCheckCircle size={18} /></span>
              </div>
              <p className="mt-3 text-[2rem] font-bold leading-none tracking-tight tabular-nums text-emerald-500">
                {data.evaluated_sheets}
              </p>
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500">
              Completed answer sheets
            </p>
          </div>

        </div>

        {/* Recent Exams Section */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-blue-950">Recent exams</h2>
            <Link
              to="/exams"
              className="group inline-flex items-center gap-1 text-sm font-semibold text-blue-600 hover:text-blue-700 transition-colors"
            >
              <span>View all</span>
              <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </Link>
          </div>

          {!data.recent_exams.length ? (
            <Empty
              title="No exams yet"
              hint="Create an exam and upload its question paper and answer key."
              action={
                <Link
                  to="/exams/new"
                  className="inline-flex items-center gap-2 rounded-full bg-blue-600 hover:bg-blue-700 px-5 py-2 text-sm font-semibold text-white shadow-sm"
                >
                  <IconPlus size={16} /> Create exam
                </Link>
              }
            />
          ) : (
            <div className="overflow-hidden rounded-2xl border border-white bg-white/90 shadow-[0_10px_30px_-20px_rgba(30,64,175,0.35)]">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-blue-100/70 bg-blue-50/40 text-xs font-bold uppercase tracking-wider text-blue-800">
                      <th className="px-6 py-3.5">Exam</th>
                      <th className="px-6 py-3.5">Class</th>
                      <th className="px-6 py-3.5">Subject</th>
                      <th className="px-6 py-3.5">Status</th>
                    </tr>
                  </thead>
                  <tbody className="stagger divide-y divide-blue-50">
                    {data.recent_exams.map((e) => (
                      <tr
                        key={e.id}
                        onClick={() => nav(`/exams/${e.id}`)}
                        className="cursor-pointer transition-colors hover:bg-blue-50/60"
                      >
                        <td className="px-6 py-4 font-semibold text-blue-950">{e.name}</td>
                        <td className="px-6 py-4 font-medium text-slate-600">{e.class_name}</td>
                        <td className="px-6 py-4 font-medium text-slate-600">{e.subject_name}</td>
                        <td className="px-6 py-4"><StatusBadge status={e.status} withDot /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>

      </div>
    </div>
  );
}
