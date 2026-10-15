import React, { useState } from "react";
import { Alert, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api } from "../api/client";
import { useTheme } from "../theme/ThemeContext";
import { Button } from "./Button";

const CANCELLABLE = ["UPLOADED", "RENDERING", "OCR_PROCESSING"];

/** Cancel button while a document is being read, and "Continue reading" after it was cancelled.
 *  Renders nothing in any other state. */
export const OcrControls: React.FC<{
  doc: { id: string; kind: string; status: string } | null | undefined;
  onChanged: () => void;
}> = ({ doc, onChanged }) => {
  const { colors } = useTheme();
  const [busy, setBusy] = useState(false);
  if (!doc) return null;

  const call = async (action: "cancel" | "reprocess") => {
    setBusy(true);
    try {
      await api(`/documents/${doc.kind}/${doc.id}/${action}`, { method: "POST" });
      onChanged();
    } catch (err: any) {
      Alert.alert(action === "cancel" ? "Could not cancel" : "Could not continue", err.message || "Please try again.");
    } finally {
      setBusy(false);
    }
  };

  if (CANCELLABLE.includes(doc.status)) {
    return (
      <Button
        title="Cancel"
        variant="outline"
        size="small"
        loading={busy}
        icon={<Ionicons name="close-circle-outline" size={15} color={colors.text} />}
        onPress={() =>
          Alert.alert("Cancel reading?", "Pages already read are kept. You can continue reading later.", [
            { text: "Keep reading", style: "cancel" },
            { text: "Cancel reading", style: "destructive", onPress: () => call("cancel") },
          ])
        }
        style={styles.btn}
      />
    );
  }
  if (doc.status === "CANCELLING") {
    return <Text style={[styles.note, { color: colors.textSecondary }]}>Stopping…</Text>;
  }
  if (doc.status === "CANCELLED") {
    return (
      <View style={styles.row}>
        <Text style={[styles.note, { color: colors.textSecondary }]}>Reading was cancelled.</Text>
        <Button
          title="Continue reading"
          variant="primary"
          size="small"
          loading={busy}
          icon={<Ionicons name="play-outline" size={15} color="#FFFFFF" />}
          onPress={() => call("reprocess")}
          style={styles.btn}
        />
      </View>
    );
  }
  return null;
};

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginTop: 8 },
  btn: { alignSelf: "flex-start", marginTop: 8 },
  note: { fontSize: 13, marginTop: 8 },
});
