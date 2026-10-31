import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Layout, type NavItem } from "./layouts/Layout";
import Login from "./pages/auth/Login";
import Signup, { VerifyEmail } from "./pages/auth/Signup";
import { ChangePassword, ForgotPassword, ResetPassword } from "./pages/auth/PasswordPages";
import * as P from "./pages/Parent";
import { IconDashboard, IconExam, IconInfo, IconResults, IconSparkles, IconStudents } from "./components/Icons";

// Every section of the Parents app
const SECTIONS: (NavItem & { title: string; what: string; page: () => JSX.Element })[] = [
  { to: "/", page: P.Dashboard, label: "Dashboard", icon: <IconDashboard />, title: "Dashboard",
    what: "For each child: recent exams and scores, progress over time, weak chapters, and your credit balance." },
  { to: "/children", page: P.Children, label: "Children", icon: <IconStudents />, title: "Children",
    what: "Add each child with their class (10 or 12) and subjects." },
  { to: "/exams", page: P.Exams, label: "Exams", icon: <IconExam />, title: "Exams",
    what: "Choose a subject, class and unit; the child sits a timed exam on screen, then you upload the answer sheet within 1 hour." },
  { to: "/reports", page: P.Reports, label: "Reports", icon: <IconResults />, title: "Reports",
    what: "Score and marked answer sheet for every exam, strengths and weak chapters, and progress by subject." },
  { to: "/credits", page: P.Credits, label: "Credits", icon: <IconSparkles />, title: "Credits",
    what: "1 credit marks 1 answer sheet. See your balance, buy credit packs and download invoices." },
  { to: "/support", page: P.Help, label: "Help", icon: <IconInfo />, title: "Help and support",
    what: "Contact support, raise a complaint about a mark, or delete your data." },
];

function LoginPage() {
  const nav = useNavigate();
  return (
    <Login
      footer={<>New to ADEM? <Link to="/signup" className="text-pen hover:underline">Create an account</Link></>}
      onNeedsSignup={(idToken) => nav("/signup", { state: { idToken } })}
    />
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/change-password" element={<ChangePassword />} />
      <Route element={<Layout nav={SECTIONS} roleLabel="Parent" />}>
        {SECTIONS.map((s) => (
          <Route key={s.to} path={s.to} element={<s.page />} />
        ))}
        <Route path="/exams/:id" element={<P.ExamRun />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
