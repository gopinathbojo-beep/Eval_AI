import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { SchoolLayout, type NavItem } from "./layouts/SchoolLayout";
import Login from "./pages/Login";
import Signup, { VerifyEmail } from "./pages/auth/Signup";
import { AcceptInvite, ChangePassword, ForgotPassword, ResetPassword } from "./pages/auth/PasswordPages";
import { IconStudents } from "./components/Icons";
import Dashboard from "./pages/Dashboard";
import { Loading } from "./components/ui";

// Dynamic lazy-loaded routes for optimal initial bundle size
const Classes = lazy(() => import("./pages/Lists").then((m) => ({ default: m.Classes })));
const Subjects = lazy(() => import("./pages/Lists").then((m) => ({ default: m.Subjects })));
const Students = lazy(() => import("./pages/Lists").then((m) => ({ default: m.Students })));
const SettingsPage = lazy(() => import("./pages/Lists").then((m) => ({ default: m.SettingsPage })));
const ExamsList = lazy(() => import("./pages/Exams").then((m) => ({ default: m.ExamsList })));
const ExamNew = lazy(() => import("./pages/Exams").then((m) => ({ default: m.ExamNew })));
const ExamWorkspace = lazy(() => import("./pages/ExamWorkspace"));
const ContentAndKey = lazy(() => import("./pages/exam/ContentAndKey"));
const Submissions = lazy(() => import("./pages/exam/Submissions"));
const ExamEvaluation = lazy(() => import("./pages/exam/Sheets").then((m) => ({ default: m.ExamEvaluation })));
const ExamResults = lazy(() => import("./pages/exam/Sheets").then((m) => ({ default: m.ExamResults })));
const EvaluationPage = lazy(() => import("./pages/EvaluationPage"));
const ResultsList = lazy(() => import("./pages/Results").then((m) => ({ default: m.ResultsList })));
const ResultPage = lazy(() => import("./pages/Results").then((m) => ({ default: m.ResultPage })));
const EvaluationsList = lazy(() => import("./pages/Results").then((m) => ({ default: m.EvaluationsList })));

const Teachers = lazy(() => import("./pages/school/Teachers"));

// School management's area; more sections join as they are built
const SCHOOL_NAV: NavItem[] = [{ to: "/school/teachers", label: "Teachers", icon: <IconStudents /> }];

const Suspended = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<Loading text="Loading workspace..." />}>{children}</Suspense>
);

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route path="/change-password" element={<ChangePassword />} />
      <Route element={<SchoolLayout nav={SCHOOL_NAV} />}>
        <Route path="/school" element={<Navigate to="/school/teachers" replace />} />
        <Route path="/school/teachers" element={<Suspended><Teachers /></Suspended>} />
      </Route>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/teacher/*" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/classes" element={<Suspended><Classes /></Suspended>} />
        <Route path="/subjects" element={<Suspended><Subjects /></Suspended>} />
        <Route path="/students" element={<Suspended><Students /></Suspended>} />
        <Route path="/settings" element={<Suspended><SettingsPage /></Suspended>} />
        <Route path="/exams" element={<Suspended><ExamsList /></Suspended>} />
        <Route path="/exams/new" element={<Suspended><ExamNew /></Suspended>} />
        <Route path="/exams/:id" element={<Suspended><ExamWorkspace /></Suspended>}>
          <Route index element={<Suspended><ContentAndKey defaultSubTab="overview" /></Suspended>} />
          <Route path="content" element={<Suspended><ContentAndKey defaultSubTab="overview" /></Suspended>} />
          <Route path="overview" element={<Suspended><ContentAndKey defaultSubTab="overview" /></Suspended>} />
          <Route path="question-paper" element={<Suspended><ContentAndKey defaultSubTab="paper" /></Suspended>} />
          <Route path="questions" element={<Suspended><ContentAndKey defaultSubTab="questions" /></Suspended>} />
          <Route path="answer-key" element={<Suspended><ContentAndKey defaultSubTab="key" /></Suspended>} />
          <Route path="submissions" element={<Suspended><Submissions defaultSubTab="sheets" /></Suspended>} />
          <Route path="students" element={<Suspended><Submissions defaultSubTab="roster" /></Suspended>} />
          <Route path="answer-sheets" element={<Suspended><Submissions defaultSubTab="sheets" /></Suspended>} />
          <Route path="evaluation" element={<Suspended><ExamEvaluation /></Suspended>} />
          <Route path="results" element={<Suspended><ExamResults /></Suspended>} />
        </Route>
        <Route path="/evaluations" element={<Suspended><EvaluationsList /></Suspended>} />
        <Route path="/evaluations/:id" element={<Suspended><EvaluationPage /></Suspended>} />
        <Route path="/results" element={<Suspended><ResultsList /></Suspended>} />
        <Route path="/results/:id" element={<Suspended><ResultPage /></Suspended>} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
