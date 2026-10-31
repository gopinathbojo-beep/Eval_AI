import { Navigate, Route, Routes } from "react-router-dom";
import { Layout, type NavItem } from "./layouts/Layout";
import Login from "./pages/auth/Login";
import { AcceptInvite, ChangePassword, ForgotPassword, ResetPassword } from "./pages/auth/PasswordPages";
import * as C from "./pages/Console";
import { useAuth } from "./context/Auth";
import {
  IconClasses, IconDashboard, IconEvaluation, IconFileText, IconResults, IconSettings, IconShieldCheck, IconSparkles,
  IconStudents, IconAlertTriangle, IconInfo,
} from "./components/Icons";

// Every section of the Admin app
const SECTIONS: (NavItem & { title: string; what: string; page: () => JSX.Element })[] = [
  { to: "/", page: C.Dashboard, label: "Dashboard", icon: <IconDashboard />, title: "Dashboard",
    what: "Totals for schools, parents and teachers, evaluations, credits sold and used, revenue, and items needing attention." },
  { to: "/schools", page: C.Schools, label: "Schools", icon: <IconClasses />, title: "Schools",
    what: "Approve new schools, suspend or delete them, reset the manager's password, and open a school for support." },
  { to: "/parents", page: C.Parents, label: "Parents", icon: <IconStudents />, title: "Parents",
    what: "Parent accounts with their children, exams, results and credit wallet." },
  { to: "/credits", page: C.Credits, label: "Credits", icon: <IconSparkles />, title: "Credits",
    what: "Credit packs and prices, credits per answer sheet, free-tier credits, manual grants and the full ledger." },
  { to: "/payments", page: C.Payments, label: "Payments", icon: <IconResults />, title: "Payments",
    what: "Razorpay orders, refunds and GST invoices." },
  { to: "/evaluations", page: C.Evaluations, label: "Evaluations", icon: <IconEvaluation />, title: "Evaluations monitor",
    what: "Running, queued and failed evaluations across all schools and parents, with retry." },
  { to: "/papers", page: C.Papers, label: "Question papers", icon: <IconFileText />, title: "Question papers",
    what: "School paper requests, the generated-paper log and the knowledge base for the paper generator." },
  { to: "/disputes", page: C.Disputes, label: "Disputes", icon: <IconAlertTriangle />, title: "Disputes",
    what: "Complaints about marks: review, resolve and refund credits." },
  { to: "/support", page: C.Support, label: "Support", icon: <IconInfo />, title: "Support tickets", what: "Questions from schools and parents." },
  { to: "/audit", page: C.Audit, label: "Audit log", icon: <IconShieldCheck />, title: "Audit log", what: "Every important action: who, what, when and from where." },
  { to: "/settings", page: C.Settings, label: "Settings", icon: <IconSettings />, title: "Settings",
    what: "Console users and roles, email, Google sign-in, GST and invoice details." },
];

const ROLE_LABEL = { super_admin: "Super Admin", admin: "Admin", viewer: "Viewer (read-only)" } as const;

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={<Login footer="Console accounts are created by a Super Admin." />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route path="/change-password" element={<ChangePassword />} />
      <Route element={<Layout nav={SECTIONS} roleLabel={user?.admin_role ? ROLE_LABEL[user.admin_role] : ""} />}>
        {SECTIONS.map((s) => (
          <Route key={s.to} path={s.to} element={<s.page />} />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
