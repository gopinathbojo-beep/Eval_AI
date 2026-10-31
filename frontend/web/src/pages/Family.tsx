import { Navigate } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { WorkspaceProfile } from "./Onboarding";
export default function Family() {
  const { teacher } = useAuth();
  return teacher?.role === "PARENT" ? (
    <div className="max-w-2xl">
      <WorkspaceProfile editing />
    </div>
  ) : (
    <Navigate to="/dashboard" replace />
  );
}
