import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import Login from "./pages/Login";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import { Loading } from "./components/ui";

// Dynamic lazy-loaded routes for optimal initial bundle size
const SettingsPage = lazy(() => import("./pages/Settings"));
const ExamsList = lazy(() =>
  import("./pages/Exams").then((m) => ({ default: m.ExamsList })),
);
const ExamNew = lazy(() =>
  import("./pages/Exams").then((m) => ({ default: m.ExamNew })),
);
const ExamWorkspace = lazy(() => import("./pages/ExamWorkspace"));
const ContentAndKey = lazy(() => import("./pages/exam/ContentAndKey"));
const Submissions = lazy(() => import("./pages/exam/Submissions"));
const UploadSheets = lazy(() => import("./pages/exam/UploadSheets"));
const EvaluationPage = lazy(() => import("./pages/EvaluationPage"));
const ResultsList = lazy(() =>
  import("./pages/Results").then((m) => ({ default: m.ResultsList })),
);
const ResultPage = lazy(() =>
  import("./pages/Results").then((m) => ({ default: m.ResultPage })),
);
const EvaluationsList = lazy(() =>
  import("./pages/Results").then((m) => ({ default: m.EvaluationsList })),
);
const Admin = lazy(() => import("./pages/Admin"));
const Register = lazy(() => import("./pages/Register"));
const RegisterChoice = lazy(() => import("./pages/Register").then((m) => ({ default: m.RegisterChoice })));
const Family = lazy(() => import("./pages/Family"));
const Onboarding = lazy(() => import("./pages/Onboarding"));
const QpGeneration = lazy(() => import("./pages/QpGeneration"));
const Uploader = lazy(() => import("./pages/Uploader"));

const Suspended = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<Loading text="Loading workspace..." />}>
    {children}
  </Suspense>
);

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/upload"
        element={
          <Suspended>
            <Uploader />
          </Suspended>
        }
      />
      <Route
        path="/register"
        element={
          <Suspended>
            <RegisterChoice />
          </Suspended>
        }
      />
      <Route
        path="/register/school"
        element={
          <Suspended>
            <Register kind="school" />
          </Suspended>
        }
      />
      <Route
        path="/register/parent"
        element={
          <Suspended>
            <Register kind="parent" />
          </Suspended>
        }
      />
      <Route
        path="/onboarding"
        element={
          <Suspended>
            <Onboarding />
          </Suspended>
        }
      />
      <Route path="/account" element={<Navigate to="/dashboard" replace />} />
      <Route element={<AppLayout />}>
        <Route
          path="/teacher/*"
          element={<Navigate to="/dashboard" replace />}
        />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route
          path="/admin"
          element={
            <Suspended>
              <Admin />
            </Suspended>
          }
        />
        <Route path="/management" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/family"
          element={
            <Suspended>
              <Family />
            </Suspended>
          }
        />
        <Route path="/classes" element={<Navigate to="/dashboard" replace />} />
        <Route path="/subjects" element={<Navigate to="/dashboard" replace />} />
        <Route path="/students" element={<Navigate to="/dashboard" replace />} />
        <Route path="/student-report" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/qp-generation"
          element={
            <Suspended>
              <QpGeneration />
            </Suspended>
          }
        />
        <Route
          path="/settings"
          element={
            <Suspended>
              <SettingsPage />
            </Suspended>
          }
        />
        <Route
          path="/exams"
          element={
            <Suspended>
              <ExamsList />
            </Suspended>
          }
        />
        <Route
          path="/exams/new"
          element={
            <Suspended>
              <ExamNew />
            </Suspended>
          }
        />
        <Route
          path="/exams/:id"
          element={
            <Suspended>
              <ExamWorkspace />
            </Suspended>
          }
        >
          <Route
            index
            element={
              <Suspended>
                <ContentAndKey defaultSubTab="questions" />
              </Suspended>
            }
          />
          <Route
            path="codes"
            element={<Navigate to="../submissions" replace />}
          />
          <Route
            path="content"
            element={
              <Suspended>
                <ContentAndKey defaultSubTab="overview" />
              </Suspended>
            }
          />
          <Route
            path="overview"
            element={
              <Suspended>
                <ContentAndKey defaultSubTab="overview" />
              </Suspended>
            }
          />
          <Route
            path="question-paper"
            element={
              <Suspended>
                <ContentAndKey defaultSubTab="paper" />
              </Suspended>
            }
          />
          <Route
            path="questions"
            element={
              <Suspended>
                <ContentAndKey defaultSubTab="questions" />
              </Suspended>
            }
          />
          <Route
            path="answer-key"
            element={
              <Suspended>
                <ContentAndKey defaultSubTab="key" />
              </Suspended>
            }
          />
          <Route
            path="submissions"
            element={
              <Suspended>
                <Submissions defaultSubTab="sheets" />
              </Suspended>
            }
          />
          <Route
            path="upload"
            element={
              <Suspended>
                <UploadSheets />
              </Suspended>
            }
          />
          <Route path="students" element={<Navigate to="../answer-sheets" replace />} />
          <Route
            path="answer-sheets"
            element={
              <Suspended>
                <Submissions defaultSubTab="sheets" />
              </Suspended>
            }
          />
          <Route path="evaluation" element={<Navigate to="../submissions" replace />} />
          <Route path="results" element={<Navigate to="../submissions" replace />} />
        </Route>
        <Route
          path="/evaluations"
          element={
            <Suspended>
              <EvaluationsList />
            </Suspended>
          }
        />
        <Route
          path="/evaluations/:id"
          element={
            <Suspended>
              <EvaluationPage />
            </Suspended>
          }
        />
        <Route
          path="/results"
          element={
            <Suspended>
              <ResultsList />
            </Suspended>
          }
        />
        <Route
          path="/results/:id"
          element={
            <Suspended>
              <ResultPage />
            </Suspended>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
