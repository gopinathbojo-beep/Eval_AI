import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, ScrollView, StyleSheet, Switch, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api, postAndShareFile } from "../../api/client";
import type { ReportTemplate, TemplateConfig, TemplateKind, Toggle } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { Loading } from "../../components/Loading";
import { ModalDialog } from "../../components/ModalDialog";

const NAMES: Record<string, string> = {
  header: "School header", title: "Title", student_details: "Student details", summary: "Summary box",
  marks_table: "Question-wise marks", subjects_table: "Subject-wise marks", outcomes: "K-level / CO summary",
  note: "Note", remarks: "Remarks", signatures: "Signatures", grade_scale: "Grading scale",
  qno: "Question no.", k_level: "K level", co: "CO", max: "Max marks", obtained: "Obtained", feedback: "Feedback",
  subject: "Subject", percent: "Percentage", grade: "Grade", percentage: "Percentage", total: "Total", rank: "Class rank",
};
const TABS = ["Layout", "Labels", "Style", "Text"] as const;
const ACCENTS = ["#1E3A5F", "#0F766E", "#111827", "#7C2D12", "#6D28D9", "#B91C1C", "#047857", "#1D4ED8"];
const CHOICES: Record<string, [string, string][]> = {
  font: [["default", "Default"], ["helvetica", "Helvetica"], ["times", "Times"]],
  logo_position: [["left", "Left"], ["center", "Above"], ["none", "Hidden"]],
  borders: [["grid", "Grid"], ["lines", "Row lines"], ["none", "None"]],
  paper: [["A4", "A4"], ["Letter", "Letter"]],
};

export const TemplateEditorScreen: React.FC<{ route: any; navigation: any }> = ({ route, navigation }) => {
  const kind: TemplateKind = route.params?.kind ?? "report";
  const { colors } = useTheme();
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [activeId, setActiveId] = useState("");
  const [selId, setSelId] = useState("");
  const [draft, setDraft] = useState<TemplateConfig | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Layout");
  const [busy, setBusy] = useState<string | null>(null);
  const [saveAsName, setSaveAsName] = useState<string | null>(null);

  useEffect(() => {
    navigation.setOptions({ title: kind === "report" ? "Exam Report Template" : "Report Card Template" });
  }, [kind, navigation]);

  const load = useCallback(async (select?: string) => {
    const r = await api<{ templates: ReportTemplate[]; active_id: string }>(`/report-templates?kind=${kind}`);
    setTemplates(r.templates);
    setActiveId(r.active_id);
    const t = r.templates.find((x) => x.id === (select ?? r.active_id)) ?? r.templates[0];
    setSelId(t.id);
    setDraft(JSON.parse(JSON.stringify(t.config)));
  }, [kind]);
  useEffect(() => {
    load().catch((e) => Alert.alert("Could Not Load", e.message || "Failed to load templates."));
  }, [load]);

  const selected = templates.find((t) => t.id === selId);
  const defaults = templates[0]?.config; // Classic: reference wording for each label
  const dirty = useMemo(() => !!selected && !!draft && JSON.stringify(selected.config) !== JSON.stringify(draft), [selected, draft]);

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await fn();
    } catch (e: any) {
      Alert.alert("Something Went Wrong", e.message || "Please try again.");
    } finally {
      setBusy(null);
    }
  };
  const set = (patch: Partial<TemplateConfig>) => {
    if (draft) setDraft({ ...draft, ...patch });
  };
  const setStyle = (patch: Partial<TemplateConfig["style"]>) => {
    if (draft) set({ style: { ...draft.style, ...patch } });
  };

  if (!draft || !defaults) return <Loading message="Loading templates..." />;

  const chip = (on: boolean) => [styles.chip, { borderColor: on ? colors.primary : colors.border, backgroundColor: on ? "rgba(7,159,189,0.15)" : colors.surface }];

  const toggleList = (key: "sections" | "columns" | "summary", title: string) => {
    const items: Toggle[] = draft[key];
    const move = (i: number, d: number) => {
      const next = [...items];
      [next[i], next[i + d]] = [next[i + d], next[i]];
      set({ [key]: next } as Partial<TemplateConfig>);
    };
    return (
      <Card style={styles.card}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>{title}</Text>
        {items.map((t, i) => (
          <View key={t.id} style={[styles.row, { borderTopColor: colors.border }]}>
            <Switch
              value={t.visible}
              onValueChange={() => set({ [key]: items.map((x) => (x.id === t.id ? { ...x, visible: !x.visible } : x)) } as Partial<TemplateConfig>)}
            />
            <Text style={{ flex: 1, color: t.visible ? colors.text : colors.textSecondary }}>{NAMES[t.id] ?? t.id}</Text>
            <TouchableOpacity disabled={i === 0} onPress={() => move(i, -1)} style={{ padding: 6, opacity: i === 0 ? 0.3 : 1 }}>
              <Ionicons name="chevron-up" size={18} color={colors.text} />
            </TouchableOpacity>
            <TouchableOpacity disabled={i === items.length - 1} onPress={() => move(i, 1)}
              style={{ padding: 6, opacity: i === items.length - 1 ? 0.3 : 1 }}>
              <Ionicons name="chevron-down" size={18} color={colors.text} />
            </TouchableOpacity>
          </View>
        ))}
      </Card>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        {/* template picker */}
        <Card style={styles.card}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>Template</Text>
          <View style={styles.wrap}>
            {templates.map((t) => (
              <TouchableOpacity key={t.id} style={chip(t.id === selId)}
                onPress={() => { setSelId(t.id); setDraft(JSON.parse(JSON.stringify(t.config))); }}>
                <Text style={{ fontWeight: "600", color: t.id === selId ? colors.primary : colors.text }}>
                  {t.name}{t.id === activeId ? "  ✓" : ""}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={{ fontSize: 11, color: colors.textSecondary, marginTop: 6 }}>✓ marks the template in use.</Text>
          <View style={[styles.wrap, { marginTop: 10 }]}>
            <Button title={selId === activeId ? "In use" : "Use this"} size="small" variant="gradient"
              disabled={selId === activeId || dirty} loading={busy === "use"}
              onPress={() => run("use", async () => {
                await api("/report-templates/activate", { method: "POST", json: { kind, id: selId } });
                setActiveId(selId);
              })} />
            {selected && !selected.preset && (
              <Button title="Save" size="small" variant="gradient" disabled={!dirty} loading={busy === "save"}
                onPress={() => run("save", async () => {
                  await api(`/report-templates/${selId}`, { method: "PUT", json: { config: draft } });
                  await load(selId);
                })} />
            )}
            <Button title="Save as new" size="small" variant="secondary"
              onPress={() => setSaveAsName(selected?.preset ? `My ${selected.name}` : `${selected?.name} copy`)} />
            <Button title="Preview PDF" size="small" variant="secondary" loading={busy === "preview"}
              onPress={() => run("preview", () => postAndShareFile("/report-templates/preview", { kind, config: draft }, `preview-${kind}.pdf`))} />
            {dirty && (
              <Button title="Undo" size="small" variant="ghost"
                onPress={() => selected && setDraft(JSON.parse(JSON.stringify(selected.config)))} />
            )}
            {selected && !selected.preset && (
              <Button title="Delete" size="small" variant="ghost" loading={busy === "del"}
                onPress={() => Alert.alert("Delete Template", `Delete "${selected.name}"?`, [
                  { text: "Cancel", style: "cancel" },
                  { text: "Delete", style: "destructive", onPress: () => run("del", async () => {
                    await api(`/report-templates/${selId}`, { method: "DELETE" });
                    await load();
                  }) },
                ])} />
            )}
          </View>
          {selected?.preset && dirty && (
            <Text style={{ fontSize: 11, color: colors.warning, marginTop: 8 }}>
              Built-in templates can't be changed. Use "Save as new" to keep your edits.
            </Text>
          )}
        </Card>

        {/* tabs */}
        <View style={[styles.tabs, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          {TABS.map((t) => (
            <TouchableOpacity key={t} onPress={() => setTab(t)} style={[styles.tab, tab === t && { backgroundColor: colors.primary }]}>
              <Text style={{ fontWeight: "700", fontSize: 12, color: tab === t ? "#FFFFFF" : colors.textSecondary }}>{t}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {tab === "Layout" && (
          <>
            {toggleList("sections", "Sections")}
            {toggleList("columns", "Table columns")}
            {toggleList("summary", "Summary box")}
          </>
        )}

        {tab === "Labels" && (
          <Card style={styles.card}>
            {Object.keys(defaults.labels).map((k) => (
              <Input key={k} label={defaults.labels[k]} value={draft.labels[k] ?? ""} placeholder={defaults.labels[k]}
                onChangeText={(v) => set({ labels: { ...draft.labels, [k]: v } })} />
            ))}
          </Card>
        )}

        {tab === "Style" && (
          <Card style={styles.card}>
            <Text style={[styles.label, { color: colors.textSecondary }]}>Accent colour</Text>
            <View style={styles.wrap}>
              {ACCENTS.map((c) => (
                <TouchableOpacity key={c} onPress={() => setStyle({ accent: c })}
                  style={[styles.swatch, { backgroundColor: c, borderColor: draft.style.accent.toUpperCase() === c ? colors.text : "transparent" }]} />
              ))}
            </View>
            <Input label="Custom colour (hex)" value={draft.style.accent} autoCapitalize="characters"
              onChangeText={(v) => setStyle({ accent: v.startsWith("#") ? v : `#${v}` })} />
            {(["font", "logo_position", "borders", "paper"] as const).map((key) => (
              <View key={key} style={{ marginBottom: 10 }}>
                <Text style={[styles.label, { color: colors.textSecondary }]}>
                  {{ font: "Font", logo_position: "Logo", borders: "Table lines", paper: "Paper" }[key]}
                </Text>
                <View style={styles.wrap}>
                  {CHOICES[key].map(([v, l]) => (
                    <TouchableOpacity key={v} style={chip(draft.style[key] === v)} onPress={() => setStyle({ [key]: v })}>
                      <Text style={{ color: draft.style[key] === v ? colors.primary : colors.text }}>{l}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            ))}
            {([["font_size", "Text size", 7, 12, 0.5], ["logo_size", "Logo size", 30, 110, 10]] as const).map(([key, l, lo, hi, step]) => (
              <View key={key} style={[styles.row, { borderTopWidth: 0 }]}>
                <Text style={{ flex: 1, color: colors.text }}>{l}: {draft.style[key]}</Text>
                <Button title="−" size="small" variant="secondary"
                  onPress={() => setStyle({ [key]: Math.max(lo, draft.style[key] - step) })} />
                <Button title="+" size="small" variant="secondary"
                  onPress={() => setStyle({ [key]: Math.min(hi, draft.style[key] + step) })} />
              </View>
            ))}
            <View style={[styles.row, { borderTopWidth: 0 }]}>
              <Text style={{ flex: 1, color: colors.text }}>Shade alternate rows</Text>
              <Switch value={draft.style.zebra} onValueChange={(v) => setStyle({ zebra: v })} />
            </View>
          </Card>
        )}

        {tab === "Text" && (
          <Card style={styles.card}>
            <Input label="Signature lines (one per line, up to 4)" multiline value={draft.signers.join("\n")}
              onChangeText={(v) => set({ signers: v.split("\n").slice(0, 4) })} />
            <Input label="Note" multiline value={draft.text.note} placeholder="e.g. Parent-teacher meeting on 12 Oct."
              onChangeText={(v) => set({ text: { ...draft.text, note: v } })} />
            <Input label="Footer (blank: school name and document)" value={draft.text.footer}
              onChangeText={(v) => set({ text: { ...draft.text, footer: v } })} />
          </Card>
        )}
      </ScrollView>

      <ModalDialog
        visible={saveAsName !== null}
        onClose={() => setSaveAsName(null)}
        title="Save as new template"
        footer={
          <Button title="Save" variant="gradient" fullWidth loading={busy === "saveas"} disabled={!saveAsName?.trim()}
            onPress={() => run("saveas", async () => {
              const t = await api<ReportTemplate>("/report-templates", {
                method: "POST", json: { kind, name: saveAsName!.trim(), config: draft },
              });
              setSaveAsName(null);
              await load(t.id);
            })} />
        }
      >
        <Input label="Name" value={saveAsName ?? ""} onChangeText={setSaveAsName} maxLength={100} autoFocus />
      </ModalDialog>
    </View>
  );
};

const styles = StyleSheet.create({
  card: { marginBottom: 12, padding: 14 },
  cardTitle: { fontSize: 14, fontWeight: "700", marginBottom: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 18, borderWidth: 1 },
  tabs: { flexDirection: "row", borderWidth: 1, borderRadius: 10, padding: 3, marginBottom: 12 },
  tab: { flex: 1, alignItems: "center", paddingVertical: 8, borderRadius: 8 },
  label: { fontSize: 12, fontWeight: "600", marginBottom: 6 },
  swatch: { width: 32, height: 32, borderRadius: 16, borderWidth: 3 },
});
