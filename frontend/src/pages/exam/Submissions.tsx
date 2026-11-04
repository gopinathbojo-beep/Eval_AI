import { AnswerSheets } from "./Sheets";

interface SubmissionsProps {
  defaultSubTab?: "sheets";
}

/** Answer sheets come from the uploader, one per typed roll number; there is no student list to manage. */
export default function Submissions(_: SubmissionsProps) {
  return <AnswerSheets />;
}
