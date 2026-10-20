import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import { Classes, Subjects, Students, SettingsPage } from "./pages/Lists";
import { ExamsList, ExamNew } from "./pages/Exams";
import ExamWorkspace from "./pages/ExamWorkspace";
import ContentAndKey from "./pages/exam/ContentAndKey";
import Submissions from "./pages/exam/Submissions";
import { ExamEvaluation, ExamResults } from "./pages/exam/Sheets";
import EvaluationPage from "./pages/EvaluationPage";
import { ResultPage, ResultsList, EvaluationsList } from "./pages/Results";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/teacher/*" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/classes" element={<Classes />} />
        <Route path="/subjects" element={<Subjects />} />
        <Route path="/students" element={<Students />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/exams" element={<ExamsList />} />
        <Route path="/exams/new" element={<ExamNew />} />
        <Route path="/exams/:id" element={<ExamWorkspace />}>
          <Route index element={<ContentAndKey defaultSubTab="overview" />} />
          <Route path="content" element={<ContentAndKey defaultSubTab="overview" />} />
          <Route path="overview" element={<ContentAndKey defaultSubTab="overview" />} />
          <Route path="question-paper" element={<ContentAndKey defaultSubTab="paper" />} />
          <Route path="questions" element={<ContentAndKey defaultSubTab="questions" />} />
          <Route path="answer-key" element={<ContentAndKey defaultSubTab="key" />} />
          <Route path="submissions" element={<Submissions defaultSubTab="sheets" />} />
          <Route path="students" element={<Submissions defaultSubTab="roster" />} />
          <Route path="answer-sheets" element={<Submissions defaultSubTab="sheets" />} />
          <Route path="evaluation" element={<ExamEvaluation />} />
          <Route path="results" element={<ExamResults />} />
        </Route>
        <Route path="/evaluations" element={<EvaluationsList />} />
        <Route path="/evaluations/:id" element={<EvaluationPage />} />
        <Route path="/results" element={<ResultsList />} />
        <Route path="/results/:id" element={<ResultPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
