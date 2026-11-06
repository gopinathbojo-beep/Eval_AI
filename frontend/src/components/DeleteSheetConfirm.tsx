import { useState } from "react";
import { api } from "../api/client";
import { Confirm } from "./ui";
import { fmt, nameIsRoll } from "../utils/format";

type Sheet = {
  id: string;
  status: string;
  total_marks?: number | null;
  maximum_marks?: number | null;
  student: { name: string; roll_number: string };
};

/** Delete a student's answer sheet with its detected answers and marks. A finalized sheet takes a second,
 *  explicit tick: its locked marks leave the results and reports. */
export function DeleteSheetConfirm({ ev, onDeleted, onClose }: {
  ev: Sheet;
  onDeleted: () => Promise<void> | void;
  onClose: () => void;
}) {
  const finalized = ev.status === "FINALIZED";
  const [sure, setSure] = useState(false);
  const who = nameIsRoll(ev.student) ? `Roll ${ev.student.roll_number}` : `${ev.student.name} (Roll ${ev.student.roll_number})`;

  return (
    <Confirm
      title="Delete answer sheet"
      danger
      confirmLabel="Delete sheet"
      body={
        <div className="space-y-2 text-sm text-ink">
          <p>
            Delete <b>{who}</b>'s answer sheet, its detected answers and all its marks?
          </p>
          {finalized && (
            <label className="flex items-start gap-2 rounded-lg border border-mark/40 bg-mark-soft p-3 text-xs">
              <input type="checkbox" className="mt-0.5 accent-mark" checked={sure}
                     onChange={(e) => setSure(e.target.checked)} />
              <span>
                This evaluation is <b>finalized</b>
                {ev.total_marks != null && <> ({fmt(ev.total_marks)} / {fmt(ev.maximum_marks)} marks)</>}.
                I understand its marks will be removed from the results and reports.
              </span>
            </label>
          )}
          <p className="text-xs text-mute">The original file is kept and the deletion is logged. You can upload the sheet again.</p>
        </div>
      }
      onConfirm={async () => {
        if (finalized && !sure) throw new Error("Tick the box to confirm deleting a finalized evaluation.");
        await api(`/evaluations/${ev.id}${finalized ? "?confirm_finalized=true" : ""}`, { method: "DELETE" });
        await onDeleted();
      }}
      onClose={onClose}
    />
  );
}
