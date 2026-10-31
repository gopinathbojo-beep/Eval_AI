import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Layout, type NavItem } from "./layouts/Layout";
import Login from "./pages/auth/Login";
import Signup, { VerifyEmail } from "./pages/auth/Signup";
import { ChangePassword, ForgotPassword, ResetPassword } from "./pages/auth/PasswordPages";
import Placeholder from "./pages/Placeholder";
import { IconDashboard, IconExam, IconInfo, IconResults, IconSparkles, IconStudents } from "./components/Icons";

// Every section of the Parents app; screens are filled in phase by phase
const SECTIONS: (NavItem & { title: string; what: string })[] = [
  { to: "/", label: "Dashboard", icon: <IconDashboard />, title: "Dashboard",
    what: "For each child: recent exams and scores, progress over time, weak chapters, and your credit balance." },
  { to: "/children", label: "Children", icon: <IconStudents />, title: "Children",
    what: "Add each child with their class (10 or 12) and subjects." },
  { to: "/exams", label: "Exams", icon: <IconExam />, title: "Exams",
    what: "Choose a subject, class and unit; the child sits a timed exam on screen, then you upload the answer sheet within 1 hour." },
  { to: "/reports", label: "Reports", icon: <IconResults />, title: "Reports",
    what: "Score and marked answer sheet for every exam, strengths and weak chapters, and progress by subject." },
  { to: "/credits", label: "Credits", icon: <IconSparkles />, title: "Credits",
    what: "1 credit marks 1 answer sheet. See your balance, buy credit packs and download invoices." },
  { to: "/support", label: "Help", icon: <IconInfo />, title: "Help and support",
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
          <Route key={s.to} path={s.to} element={<Placeholder title={s.title} what={s.what} />} />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
