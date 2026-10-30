import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTheme } from "../theme/ThemeContext";
import type { OutcomeRow, Outcomes } from "../types";
import { Card } from "./Card";

const fmt = (n: number | undefined) => (n === undefined ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(1));

function OutcomeCard({ title, rows }: { title: string; rows: OutcomeRow[] }) {
  const { colors } = useTheme();
  return (
    <Card style={styles.card}>
      <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      {rows.map((r) => (
        <View key={r.key} style={[styles.row, { borderTopColor: colors.border }]}>
          <View style={{ width: 110 }}>
            <Text style={{ fontWeight: "700", color: colors.text }}>{r.key}</Text>
            {r.label !== r.key && <Text style={{ fontSize: 11, color: colors.textSecondary }}>{r.label}</Text>}
          </View>
          <View style={{ flex: 1, gap: 4 }}>
            <View style={[styles.track, { backgroundColor: colors.surfaceElevated }]}>
              <View style={[styles.fill, { backgroundColor: colors.primaryFill, width: `${Math.min(100, r.percentage ?? 0)}%` }]} />
            </View>
            <Text style={{ fontSize: 11, color: colors.textSecondary }}>
              {fmt(r.scored ?? r.average_scored)} / {fmt(r.max_marks)} marks
              {r.percentage !== null ? `  •  ${r.percentage}%` : ""}
            </Text>
          </View>
        </View>
      ))}
    </Card>
  );
}

/** Marks grouped by course outcome; hidden when no question is tagged. */
export const OutcomeTables: React.FC<{ outcomes: Outcomes }> = ({ outcomes }) => {
  const tagged = (rows: OutcomeRow[]) => rows.some((r) => r.key !== "Untagged");
  return (
    <>
      {tagged(outcomes.course_outcomes) && <OutcomeCard title="Performance by Course Outcome" rows={outcomes.course_outcomes} />}
    </>
  );
};

const styles = StyleSheet.create({
  card: { marginBottom: 14, padding: 14 },
  title: { fontSize: 14, fontWeight: "700", marginBottom: 6 },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth },
  track: { height: 6, borderRadius: 3, overflow: "hidden" },
  fill: { height: 6, borderRadius: 3 },
});
