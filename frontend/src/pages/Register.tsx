import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import RegistrationChat, {
  type ChatStep,
} from "../components/RegistrationChat";
import { Loading } from "../components/ui";

export const roleStep: ChatStep = {
  key: "role",
  label: "Account type",
  question: "Who are you joining Eval AI as?",
  choices: [
    {
      value: "MANAGEMENT",
      label: "School management",
      description:
        "Create a school workspace, add teachers and manage evaluations.",
    },
    {
      value: "PARENT",
      label: "Parent",
      description:
        "Evaluate your child’s answer sheets in a private family workspace.",
    },
  ],
};

export default function Register() {
  const { teacher, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const { data: providers } = useApi<{
    google: boolean;
    google_start_url: string;
  }>("/auth/providers");
  const [values, setValues] = useState<Record<string, string>>({});
  const steps: ChatStep[] = [
    roleStep,
    {
      key: "name",
      label: "Full name",
      question: "Lovely. What’s your full name?",
      autoComplete: "name",
    },
    {
      key: "email",
      label: "Email address",
      question: "Which email address would you like to use?",
      type: "email",
      autoComplete: "email",
      hint: "You’ll use this email to log in to Eval AI.",
    },
    {
      key: "password",
      label: "Password",
      question: "Let’s secure your account. Choose a password.",
      type: "password",
      autoComplete: "new-password",
      maxLength: 72,
      hint: "Use at least 10 characters. Your password won’t appear in the chat.",
    },
    {
      key: "confirm",
      label: "Confirm password",
      question: "Please enter your password once more to confirm it.",
      type: "password",
      autoComplete: "new-password",
      maxLength: 72,
    },
  ];
  if (loading) return <Loading />;
  if (teacher)
    return (
      <Navigate
        to={
          teacher.is_admin
            ? "/admin"
            : teacher.profile_complete
              ? "/dashboard"
              : "/onboarding"
        }
        replace
      />
    );
  return (
    <RegistrationChat
      title="A conversation, then you’re in."
      intro="Tell us a little about yourself. We’ll set up the right space for your school or your child, one question at a time."
      steps={steps}
      values={values}
      onAnswer={(key, value) =>
        setValues((previous) => ({ ...previous, [key]: value }))
      }
      validate={(key, value) => {
        if (
          key === "password" &&
          (value.length < 10 || new TextEncoder().encode(value).length > 72)
        )
          return "Use at least 10 characters and no more than 72 bytes for your password.";
        if (key === "confirm" && value !== values.password)
          return "That doesn’t match your password. Please try again.";
      }}
      googleUrl={providers?.google ? providers.google_start_url : undefined}
      submitLabel="Create account"
      onSubmit={async () => {
        if (values.password !== values.confirm)
          throw new Error(
            "Passwords do not match. Edit the confirmation to continue.",
          );
        await api("/auth/register", {
          method: "POST",
          json: {
            name: values.name,
            email: values.email,
            password: values.password,
            role: values.role,
          },
        });
        await refresh();
        navigate("/onboarding", { replace: true });
      }}
    />
  );
}
