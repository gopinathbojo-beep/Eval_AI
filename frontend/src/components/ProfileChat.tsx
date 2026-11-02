import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import RegistrationChat, { type ChatStep } from "./RegistrationChat";
import { roleStep } from "../pages/Register";

export default function ProfileChat() {
  const { teacher, refresh } = useAuth();
  const [values, setValues] = useState<Record<string, string>>({
    name: teacher?.name ?? "",
    role: teacher?.role === "PARENT" ? "PARENT" : "MANAGEMENT",
    ...Object.fromEntries(
      Object.entries(teacher?.profile ?? {}).map(([key, value]) => [
        key,
        String(value ?? ""),
      ]),
    ),
  });
  const steps: ChatStep[] = [
    ...(teacher?.role === "UNASSIGNED" ? [roleStep] : []),
    {
      key: "name",
      label: "Contact name",
      question: `What name should we use for your ${values.role === "PARENT" ? "parent" : "school management"} profile?`,
      autoComplete: "name",
    },
    {
      key: "phone",
      label: "Contact number",
      question: "What’s your contact number?",
      type: "tel",
      autoComplete: "tel",
      maxLength: 30,
    },
    ...(values.role === "PARENT"
      ? [
          {
            key: "child_name",
            label: "Child’s full name",
            question: "What’s your child’s full name?",
            hint: "Their evaluations will stay private to your family. One child per account.",
          },
          {
            key: "child_class",
            label: "Child’s class",
            question: "Which CBSE class is your child in?",
            choices: [
              { value: "10", label: "Class 10" },
              { value: "12", label: "Class 12" },
            ],
          },
          {
            key: "school_name",
            label: "Child’s school",
            question: "Which school does your child attend?",
            optional: true,
            hint: "This is optional. You can skip it for now.",
          },
        ]
      : [
          {
            key: "school_name",
            label: "School name",
            question: "What’s the name of your school?",
            autoComplete: "organization",
          },
          {
            key: "address",
            label: "School address",
            question: "What’s your school’s street address?",
            autoComplete: "street-address",
            maxLength: 600,
          },
          {
            key: "city",
            label: "City",
            question: "Which city is your school in?",
            autoComplete: "address-level2",
            maxLength: 100,
          },
          {
            key: "state",
            label: "State",
            question: "Which state is it in?",
            autoComplete: "address-level1",
            maxLength: 100,
          },
          {
            key: "postcode",
            label: "Postcode",
            question: "What’s the school’s postcode?",
            autoComplete: "postal-code",
            maxLength: 20,
          },
          {
            key: "principal_name",
            label: "Principal name",
            question: "Would you like to add the principal’s name?",
            optional: true,
            hint: "Optional. You can add this later in your school profile.",
          },
          {
            key: "affiliation_number",
            label: "CBSE affiliation number",
            question: "Do you have a CBSE affiliation number to add?",
            maxLength: 50,
            optional: true,
            hint: "Optional. Your board is set to CBSE.",
          },
        ]),
  ];
  return (
    <RegistrationChat
      title={
        values.role === "PARENT"
          ? "A space for your child to grow."
          : "Let’s make this your school’s space."
      }
      intro="Your account is ready. A few more details will help us personalise your workspace. You can review everything before continuing."
      steps={steps}
      values={values}
      onAnswer={(key, value) =>
        setValues((previous) => ({ ...previous, [key]: value }))
      }
      submitLabel="Open my workspace"
      onSubmit={async () => {
        const keys = new Set(steps.map((step) => step.key));
        const profile = Object.fromEntries(
          Object.entries(values).filter(([key]) => keys.has(key)),
        );
        await api("/auth/profile", {
          method: "PUT",
          json: {
            ...profile,
            role: values.role,
            child_class: values.role === "PARENT" ? values.child_class : null,
          },
        });
        await refresh();
      }}
    />
  );
}
