import React, { useCallback, useEffect, useState } from "react";
import { Alert, Text, TouchableOpacity, View } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { useTheme } from "../theme/ThemeContext";
import { api, downloadAndShareFile, uploadFileNative } from "../api/client";
import type { ReportCardTerm, SchoolProfile } from "../types";
import { Card } from "./Card";
import { Button } from "./Button";
import { Input } from "./Input";
import { AuthImage } from "./AuthImage";
import { ModalDialog } from "./ModalDialog";

/** School name, address, principal and logo: printed on every report and report card. */
export const SchoolDetailsCard: React.FC = () => {
  const { colors } = useTheme();
  const [profile, setProfile] = useState<SchoolProfile | null>(null);
  const [form, setForm] = useState({ name: "", address: "", principal_name: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [logoVersion, setLogoVersion] = useState(0);

  const load = useCallback(async () => {
    const p = await api<SchoolProfile>("/school-profile");
    setProfile(p);
    setForm({ name: p.name, address: p.address, principal_name: p.principal_name });
  }, []);
  useEffect(() => {
    load().catch(() => setProfile(null));
  }, [load]);

  const run = async (key: string, fn: () => Promise<unknown>, done?: string) => {
    setBusy(key);
    try {
      await fn();
      await load();
      if (done) Alert.alert("Saved", done);
    } catch (e: any) {
      Alert.alert("Something Went Wrong", e.message || "Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const pickLogo = async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: ["image/png", "image/jpeg"], copyToCacheDirectory: true });
    if (res.canceled || !res.assets?.length) return;
    const f = res.assets[0];
    await run("logo", async () => {
      await uploadFileNative("/school-profile/logo", f.uri, { fileName: f.name, mimeType: f.mimeType });
      setLogoVersion((v) => v + 1);
    });
  };

  return (
    <Card style={{ marginBottom: 14, padding: 16 }}>
      <Text style={{ fontSize: 16, fontWeight: "700", color: colors.text }}>School Details</Text>
      <Text style={{ fontSize: 12, color: colors.textSecondary, marginBottom: 12 }}>Printed at the top of reports and report cards.</Text>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <View style={{ width: 64, height: 64, borderRadius: 10, borderWidth: 1, borderColor: colors.border, overflow: "hidden",
                       alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceElevated }}>
          {profile?.has_logo ? (
            <AuthImage key={logoVersion} path={`/school-profile/logo?v=${logoVersion}`} style={{ width: 60, height: 60, resizeMode: "contain" } as any} />
          ) : (
            <Text style={{ fontSize: 11, color: colors.textSecondary }}>No logo</Text>
          )}
        </View>
        <View style={{ flex: 1, gap: 6 }}>
          <Button title={profile?.has_logo ? "Change logo" : "Upload logo"} size="small" variant="secondary"
            loading={busy === "logo"} onPress={pickLogo} />
          {profile?.has_logo && (
            <Button title="Remove logo" size="small" variant="ghost" loading={busy === "dellogo"}
              onPress={() => run("dellogo", () => api("/school-profile/logo", { method: "DELETE" }))} />
          )}
        </View>
      </View>
      <Input label="School name" value={form.name} maxLength={200} onChangeText={(name) => setForm({ ...form, name })} />
      <Input label="Address" value={form.address} multiline maxLength={600} onChangeText={(address) => setForm({ ...form, address })} />
      <Input label="Principal's name" value={form.principal_name} maxLength={200}
        onChangeText={(principal_name) => setForm({ ...form, principal_name })} />
      <Button title="Save School Details" variant="gradient" fullWidth loading={busy === "save"}
        onPress={() => run("save", () => api("/school-profile", { method: "PUT", json: form }), "School details updated.")} />
    </Card>
  );
};

/** Pick a term and download report cards for one student or a whole class. */
export const ReportCardModal: React.FC<{
  visible: boolean; classId: string | null; studentId?: string; title: string; onClose: () => void;
}> = ({ visible, classId, studentId, title, onClose }) => {
  const { colors } = useTheme();
  const [terms, setTerms] = useState<ReportCardTerm[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || !classId) return;
    setTerms(null);
    api<ReportCardTerm[]>(`/classes/${classId}/report-card-terms`).then(setTerms).catch(() => setTerms([]));
  }, [visible, classId]);

  const download = async (t: ReportCardTerm) => {
    const key = `${t.academic_year}-${t.exam_type}`;
    const q = `academic_year=${encodeURIComponent(t.academic_year)}&exam_type=${encodeURIComponent(t.exam_type)}`;
    setBusy(key);
    try {
      await downloadAndShareFile(studentId ? `/students/${studentId}/report-card?${q}` : `/classes/${classId}/report-cards?${q}`,
        `ReportCard_${t.exam_type}_${t.academic_year}.pdf`);
      onClose();
    } catch (e: any) {
      Alert.alert("Download Failed", e.message || "Could not create the report card.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <ModalDialog visible={visible} onClose={onClose} title={title} subtitle="Choose the term">
      {terms === null ? (
        <Text style={{ color: colors.textSecondary }}>Loading terms…</Text>
      ) : terms.length === 0 ? (
        <Text style={{ color: colors.textSecondary }}>No finalized results yet for this class.</Text>
      ) : (
        <View style={{ gap: 8 }}>
          {terms.map((t) => {
            const key = `${t.academic_year}-${t.exam_type}`;
            return (
              <TouchableOpacity key={key} disabled={!!busy} onPress={() => download(t)}
                style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: 12, opacity: busy && busy !== key ? 0.5 : 1 }}>
                <Text style={{ fontWeight: "700", color: colors.text }}>{t.exam_type} · {t.academic_year}</Text>
                <Text style={{ fontSize: 12, color: colors.textSecondary }}>
                  {busy === key ? "Preparing PDF…" : t.subjects.join(", ")}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      )}
    </ModalDialog>
  );
};
