import { Navigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { PageCanvas, PageHeader } from "../components/ui";
import {
  ReportTemplatesCard,
  SchoolDetailsCard,
} from "../components/SchoolSettings";

export default function SettingsPage() {
  const { teacher } = useAuth();
  if (teacher?.role !== "MANAGEMENT") return <Navigate to="/dashboard" replace />;
  return (
    <PageCanvas className="max-w-4xl">
      <PageHeader title="Settings" sub="School details and report templates." />
      <SchoolDetailsCard />
      <ReportTemplatesCard />
    </PageCanvas>
  );
}

