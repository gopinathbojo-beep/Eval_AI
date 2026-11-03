import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/Auth";
import RegistrationChat, { type ChatStep } from "./RegistrationChat";
import { roleStep } from "../pages/Register";
import { nameProblem, phoneProblem, pinProblem, placeProblem } from "../utils/validation";

/** What CBSE SARAS publishes for an affiliation number (see GET /auth/affiliation/{number}). */
interface CbseSchool {
  affiliation_number: string;
  school_name: string;
  address: string;
  district: string;
  city?: string;
  state: string;
  postcode: string;
  principal_name: string;
  school_level?: string;
  affiliation_to?: string;
}

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

  const [directSchool, setDirectSchool] = useState<CbseSchool | null>(null);
  const [directMissed, setDirectMissed] = useState(false);
  const [searchResults, setSearchResults] = useState<CbseSchool[] | null>(null);
  const [searchDone, setSearchDone] = useState(false);

  // Look up school by affiliation number directly from Step 1
  const lookUpDirect = async (number: string) => {
    if (!number || !number.trim()) {
      setDirectSchool(null);
      setDirectMissed(false);
      return;
    }
    const cleanNum = number.trim();
    if (directSchool?.affiliation_number === cleanNum) return;
    try {
      const school = await api<CbseSchool>(`/auth/affiliation/${encodeURIComponent(cleanNum)}`);
      setValues((v) => ({
        ...v,
        affiliation_number: school.affiliation_number || cleanNum,
        school_name: school.school_name || v.school_name,
        building: school.address || v.building,
        city: school.district || v.city,
        state: school.state || v.state,
        postcode: school.postcode || v.postcode,
        principal_name: school.principal_name || v.principal_name,
      }));
      setDirectSchool(school);
      setDirectMissed(false);
    } catch {
      setDirectSchool(null);
      setDirectMissed(true);
    }
  };

  // Search schools by name in CBSE records (when affiliation was skipped or not found)
  const searchSchoolByName = async (schoolName: string) => {
    if (!schoolName || schoolName.trim().length < 2) return;
    try {
      const results = await api<CbseSchool[]>(`/auth/school-search?q=${encodeURIComponent(schoolName.trim())}`);
      setSearchResults(results && results.length > 0 ? results : []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearchDone(true);
    }
  };

  // Select a school from the search results
  const selectSchool = async (affNumber: string) => {
    if (!affNumber || affNumber === "manual") {
      return;
    }
    const matched = searchResults?.find((s) => s.affiliation_number === affNumber);
    if (matched) {
      setValues((v) => ({
        ...v,
        affiliation_number: matched.affiliation_number,
        school_name: matched.school_name || v.school_name,
        building: matched.address || v.building,
        city: matched.district || v.city,
        state: matched.state || v.state,
        postcode: matched.postcode || v.postcode,
        principal_name: matched.principal_name || v.principal_name,
      }));
    }
    try {
      const full = await api<CbseSchool>(`/auth/affiliation/${encodeURIComponent(affNumber)}`);
      setValues((v) => ({
        ...v,
        affiliation_number: full.affiliation_number || affNumber,
        school_name: full.school_name || v.school_name,
        building: full.address || v.building,
        city: full.district || full.city || v.city,
        state: full.state || v.state,
        postcode: full.postcode || v.postcode,
        principal_name: full.principal_name || v.principal_name,
      }));
    } catch {
      // ignore if full details endpoint unavailable, we already populated from matched
    }
  };

  // Build steps dynamically based on what was found and what is missing
  const steps: ChatStep[] = [
    ...(teacher?.role === "UNASSIGNED" ? [roleStep] : []),

    ...(values.role === "PARENT"
      ? [
          {
            key: "name",
            label: "Parent name",
            question: "What name should we use for your parent profile?",
            autoComplete: "name",
          },
          {
            key: "phone",
            label: "Contact number",
            question: "What’s your contact number?",
            type: "tel" as const,
            autoComplete: "tel",
            maxLength: 30,
          },
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
          // Step 1: CBSE Affiliation Number with prominent Skip button
          {
            key: "affiliation_number",
            label: "CBSE affiliation number",
            question: "Do you have a CBSE affiliation number to add?",
            maxLength: 10,
            optional: true,
            hint: "If you have it, enter your number and we’ll automatically map your school’s details from CBSE records. Otherwise, click Skip.",
            busyText: "Looking up your school in CBSE records…",
            onAnswered: lookUpDirect,
          },

          // Step 2A: If CBSE affiliation number is given & found -> Map data & skip manual address/principal inputs!
          ...(directSchool
            ? [
                {
                  key: "school_details",
                  label: "School details",
                  question: "Here’s what CBSE has on record for your school. Please check each detail and confirm.",
                  cardTitle: "Details from CBSE records",
                  cardNote: [
                    directSchool.affiliation_number && `Affiliation ${directSchool.affiliation_number}`,
                    directSchool.school_level,
                    directSchool.affiliation_to && `affiliated until ${directSchool.affiliation_to}`,
                  ].filter(Boolean).join(" · "),
                  submitText: "Confirm details",
                  fields: [
                    { key: "school_name", label: "School name", autoComplete: "organization", wide: true },
                    { key: "building", label: "Address", autoComplete: "street-address", wide: true },
                    { key: "city", label: "City / District", autoComplete: "address-level2", maxLength: 100 },
                    { key: "state", label: "State", autoComplete: "address-level1", maxLength: 100 },
                    { key: "postcode", label: "PIN Code", autoComplete: "postal-code", maxLength: 6, inputMode: "numeric" as const },
                    { key: "principal_name", label: "Principal / Head", autoComplete: "off" },
                  ],
                  format: (v: Record<string, string>) =>
                    `${v.school_name}\n${[v.building, v.city, v.state].filter(Boolean).join(", ")}${v.postcode ? ` - ${v.postcode}` : ""}\nPrincipal: ${v.principal_name}`,
                },
              ]
            : [
                // Step 2B: If affiliation number skipped or not found -> Ask School Name
                {
                  key: "school_name",
                  label: "School name",
                  question: directMissed
                    ? "We couldn’t find that affiliation number in CBSE records. What is your school’s name?"
                    : "What is your school’s name?",
                  hint: "We’ll search CBSE records for your school name to fetch your details.",
                  autoComplete: "organization",
                  busyText: "Searching CBSE records for your school…",
                  onAnswered: searchSchoolByName,
                },

                // Step 2C: If search returned matches, show them to select!
                ...(searchDone && searchResults && searchResults.length > 0
                  ? [
                      {
                        key: "selected_school",
                        label: "Select your school",
                        question: `We found ${searchResults.length} matching school${searchResults.length > 1 ? "s" : ""} in CBSE records. Select yours:`,
                        choices: [
                          ...searchResults.map((s) => ({
                            value: s.affiliation_number,
                            label: s.school_name,
                            description: [s.address || s.district, s.state, `Affiliation: ${s.affiliation_number}`]
                              .filter(Boolean)
                              .join(" · "),
                          })),
                          {
                            value: "manual",
                            label: "None of these / Enter details manually",
                            description: "Enter your school’s address and details by hand",
                          },
                        ],
                        onAnswered: selectSchool,
                      },
                    ]
                  : []),

                // Step 2D: Ask for missing details!
                // If address is missing, or manual chosen
                ...(!values.building || !values.city || !values.state || values.selected_school === "manual"
                  ? [
                      {
                        key: "address",
                        label: "School address",
                        question: "What is your school’s complete address?",
                        cardTitle: "School address details",
                        submitText: "Submit Address",
                        fields: [
                          { key: "building", label: "Building / Campus Name", placeholder: "e.g. Green Valley Campus", autoComplete: "address-line1", wide: true },
                          { key: "locality", label: "Locality / Area", placeholder: "e.g. Anna Nagar", autoComplete: "address-line2", wide: true },
                          { key: "city", label: "City", placeholder: "e.g. Chennai", autoComplete: "address-level2", maxLength: 100 },
                          { key: "state", label: "State", placeholder: "e.g. Tamil Nadu", autoComplete: "address-level1", maxLength: 100 },
                          { key: "postcode", label: "PIN Code", placeholder: "6 digits", autoComplete: "postal-code", maxLength: 6, inputMode: "numeric" as const },
                        ],
                        format: (v: Record<string, string>) =>
                          `${[v.building, v.locality, v.city, v.state].filter(Boolean).join(", ")}${v.postcode ? ` - ${v.postcode}` : ""}`,
                      },
                    ]
                  : [
                      // If address is present but PIN code is missing:
                      ...(!values.postcode
                        ? [
                            {
                              key: "postcode",
                              label: "PIN Code",
                              question: "What is your school’s 6-digit PIN code?",
                              maxLength: 6,
                            },
                          ]
                        : []),
                    ]),

                // If Principal name is missing
                ...(!values.principal_name || values.selected_school === "manual"
                  ? [
                      {
                        key: "principal_name",
                        label: "Principal name",
                        question: "What is the name of your school’s Principal or Head?",
                        autoComplete: "off",
                      },
                    ]
                  : []),
              ]),

          // Contact Details (Contact name if not yet set, plus Contact number)
          ...(!values.name
            ? [
                {
                  key: "name",
                  label: "Contact name",
                  question: "What name should we use for your school management profile?",
                  autoComplete: "name",
                },
              ]
            : []),
          {
            key: "phone",
            label: "Contact number",
            question: "What’s your contact number?",
            type: "tel" as const,
            autoComplete: "tel",
            maxLength: 30,
            hint: "We’ll use this number for critical exam and evaluation notifications.",
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
      validate={(key, value) => {
        const problem =
          key === "name" ? nameProblem(value, "Name")
          : key === "phone" ? phoneProblem(value)
          : key === "child_name" ? nameProblem(value, "Your child’s name")
          : key === "principal_name" ? nameProblem(value, "Principal’s name")
          : key === "school_name" && value ? placeProblem(value, "School name")
          : key === "affiliation_number" && value && !/^\d{4,10}$/.test(value)
            ? "A CBSE affiliation number has only digits, like 1930001."
          : key === "building" ? placeProblem(value, "Building / Institution name")
          : key === "locality" ? placeProblem(value, "Locality")
          : key === "city" ? placeProblem(value, "City")
          : key === "state" ? placeProblem(value, "State")
          : key === "postcode" ? pinProblem(value)
          : null;
        return problem ?? undefined;
      }}
      submitLabel="Open my workspace"
      onSubmit={async () => {
        // Collect all profile-relevant fields answered or mapped from CBSE records
        const allowed = [
          "name",
          "role",
          "phone",
          "school_name",
          "address",
          "building",
          "locality",
          "city",
          "state",
          "postcode",
          "principal_name",
          "affiliation_number",
          "child_name",
          "child_class",
        ];
        const profile = Object.fromEntries(
          Object.entries(values).filter(([k, v]) => allowed.includes(k) && v !== undefined && v !== ""),
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
