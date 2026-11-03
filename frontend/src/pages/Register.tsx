import { useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import RegistrationChat, { type ChatStep } from "../components/RegistrationChat";
import { BrandLabel } from "../components/Brand";
import { Loading } from "../components/ui";
import { emailProblem, nameProblem, passwordProblem } from "../utils/validation";

export type RegistrationKind = "school" | "parent";

/** Still used by onboarding for Google accounts that have not picked a type yet. */
export const roleStep: ChatStep = {
  key: "role",
  label: "Account type",
  question: "Who are you joining Eval AI as?",
  choices: [
    { value: "MANAGEMENT", label: "School management", description: "Create your school's workspace, set up exams and evaluate answer sheets." },
    { value: "PARENT", label: "Parent", description: "Evaluate your child's answer sheets in a private family workspace." },
  ],
};

/** /register: how would you like to register? Teachers never self-register. */
export function RegisterChoice({ onPick }: { onPick?: (kind: RegistrationKind) => void }) {
  const { teacher, loading } = useAuth();
  if (loading) return <Loading />;
  if (teacher && !onPick) return <Navigate to={home(teacher)} replace />;
  const card = "block rounded-xl border border-line bg-surface p-6 text-left shadow-card transition-ui hover:border-pen hover:bg-pen-soft/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-pen";
  return (
    <main className="app-shell app-bg flex min-h-screen flex-col px-5 sm:px-10">
      <header className="mx-auto flex w-full max-w-4xl items-center justify-between py-6">
        <Link to="/" aria-label="Eval AI home"><BrandLabel onDark={false} /></Link>
        <Link to="/login" className="text-sm font-semibold text-pen hover:underline">Login</Link>
      </header>
      <section className="mx-auto w-full max-w-2xl flex-1 py-10 sm:py-16">
        <p className="max-w-md rounded-2xl rounded-tl-sm bg-sunken px-5 py-4 font-display text-xl">
          Hi! How would you like to register?
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {([["school", "School Management", "Set up your school's workspace: exams, answer sheets and reports."],
             ["parent", "Parent", "A private space for your child's exams and progress."]] as const).map(([kind, label, text]) => {
            const body = (
              <>
                <span className="block text-lg font-semibold text-pen">{label}</span>
                <span className="mt-2 block text-sm text-mute">{text}</span>
              </>
            );
            return onPick ? (
              <button key={kind} type="button" onClick={() => onPick(kind)} className={card}>{body}</button>
            ) : (
              <Link key={kind} to={`/register/${kind}`} className={card}>{body}</Link>
            );
          })}
        </div>
        <p className="mt-8 text-sm text-mute">
          Already registered? <Link to="/login" className="font-semibold text-pen underline">Login</Link>
        </p>
      </section>
    </main>
  );
}

const home = (t: { is_admin: boolean; profile_complete: boolean; must_change_password?: boolean }) =>
  t.is_admin ? "/admin" : t.profile_complete ? "/dashboard" : "/onboarding";

/** The original sign-up questions; the account type comes from the School / Parent choice. */
const ACCOUNT_STEPS: ChatStep[] = [
  { key: "name", label: "Full name", question: "Lovely. What’s your full name?", autoComplete: "name" },
  { key: "email", label: "Email address", question: "Which email address would you like to use?", type: "email",
    autoComplete: "email", hint: "You’ll use this email to log in to Eval AI." },
  { key: "password", label: "Password", question: "Let’s secure your account. Choose a password.", type: "password",
    autoComplete: "new-password", maxLength: 72, hint: "At least 8 characters, starting with a capital letter, 1 number, and 1 special character." },
  { key: "confirm", label: "Confirm password", question: "Please enter your password once more to confirm it.",
    type: "password", autoComplete: "new-password", maxLength: 72 },
];

/** Account sign-up chat; the school or family details follow in onboarding (ProfileChat). */
function AccountChat({ kind }: { kind: RegistrationKind }) {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const { data: providers } = useApi<{ google: boolean; google_start_url: string }>("/auth/providers");
  const [values, setValues] = useState<Record<string, string>>({});
  return (
    <RegistrationChat
      title="A conversation, then you’re in."
      intro={kind === "school"
        ? "Tell us a little about yourself. We’ll set up your school’s space, one question at a time."
        : "Tell us a little about yourself. We’ll set up a space for your child, one question at a time."}
      steps={ACCOUNT_STEPS}
      values={values}
      onAnswer={(key, value) => setValues((previous) => ({ ...previous, [key]: value }))}
      validate={(key, value) => {
        const problem = key === "name" ? nameProblem(value, "Your name")
          : key === "email" ? emailProblem(value)
          : key === "password" ? passwordProblem(value)
          : key === "confirm" && value !== values.password ? "That doesn’t match your password. Please try again."
          : null;
        return problem ?? undefined;
      }}
      googleUrl={providers?.google ? providers.google_start_url : undefined}
      submitLabel="Create account"
      onSubmit={async () => {
        if (values.password !== values.confirm)
          throw new Error("Passwords do not match. Edit the confirmation to continue.");
        try {
          await api("/auth/register", { method: "POST", json: {
            name: values.name, email: values.email, password: values.password,
            role: kind === "school" ? "MANAGEMENT" : "PARENT" } });
        } catch (e) {
          if (e instanceof ApiError && e.code === "EMAIL_EXISTS")
            throw new Error("An account with this email already exists. Edit the email, or log in instead.");
          throw e;
        }
        await refresh();
        navigate("/onboarding", { replace: true });
      }}
    />
  );
}

/** /register/school and /register/parent */
export default function Register({ kind }: { kind: RegistrationKind }) {
  const { teacher, loading } = useAuth();
  // Redirect only someone who arrived signed in; during this flow the account appears half way through.
  const arrivedSignedIn = useRef<boolean | null>(null);
  if (loading) return <Loading />;
  if (arrivedSignedIn.current === null) arrivedSignedIn.current = !!teacher;
  if (arrivedSignedIn.current && teacher) return <Navigate to={home(teacher)} replace />;
  return <AccountChat kind={kind} />;
}
