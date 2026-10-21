import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../theme/ThemeContext";
import { getBaseUrl, setBaseUrl, api } from "../../api/client";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { Badge } from "../../components/Badge";
import { SchoolDetailsCard } from "../../components/SchoolReports";

export const SettingsScreen: React.FC<{ navigation?: any }> = ({ navigation }) => {
  const { teacher, logout } = useAuth();
  const { mode, colors, setMode } = useTheme();

  const [serverUrl, setServerUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [connectionMessage, setConnectionMessage] = useState<string | null>(null);

  // AI Status
  const [aiStatus, setAiStatus] = useState<any>(null);
  const [checkingAi, setCheckingAi] = useState(false);

  useEffect(() => {
    getBaseUrl().then(setServerUrl);
    checkAiStatus();
  }, []);

  const checkAiStatus = async () => {
    try {
      setCheckingAi(true);
      const res = await api<any>("/system/ai-status");
      setAiStatus(res);
    } catch (err: any) {
      setAiStatus({ available: false, message: err.message || "Failed to reach AI service" });
    } finally {
      setCheckingAi(false);
    }
  };

  const handleSaveAndTestUrl = async () => {
    if (!serverUrl.trim()) {
      Alert.alert("Validation", "Server URL cannot be empty.");
      return;
    }
    try {
      setTesting(true);
      setConnectionMessage(null);
      await setBaseUrl(serverUrl);
      const res = await fetch(`${serverUrl.trim().replace(/\/+$/, "")}/api/health`);
      if (res.ok) {
        setConnectionMessage("Connected to Eval AI backend successfully!");
        checkAiStatus();
      } else {
        setConnectionMessage(`Server returned HTTP ${res.status}.`);
      }
    } catch (err: any) {
      setConnectionMessage(`Connection failed. Check IP/port and firewall.`);
    } finally {
      setTesting(false);
    }
  };

  const handleLogout = () => {
    Alert.alert("Sign Out", "Are you sure you want to sign out of Eval AI?", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign Out", style: "destructive", onPress: logout },
    ]);
  };

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.background }]}
      contentContainerStyle={styles.content}
    >
      {/* Profile Card */}
      <Card style={styles.card}>
        <View style={styles.profileHeader}>
          <View
            style={[
              styles.avatar,
              { backgroundColor: "rgba(7, 159, 189, 0.15)", borderColor: colors.primary },
            ]}
          >
            <Ionicons name="person" size={28} color={colors.primary} />
          </View>
          <View style={{ flex: 1, marginLeft: 14 }}>
            <Text style={[styles.nameText, { color: colors.text }]}>{teacher?.name}</Text>
            <Text style={[styles.emailText, { color: colors.textSecondary }]}>
              {teacher?.email}
            </Text>
            <Text style={[styles.roleBadge, { color: colors.brandGreen }]}>
              Verified Teacher • School Examiner
            </Text>
          </View>
        </View>
      </Card>

      {/* Theme Settings */}
      <Card style={styles.card}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>Appearance & Theme</Text>
        <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
          Choose between Eval AI dark mode, clean light mode, or match system settings.
        </Text>

        <View style={styles.themeOptionsRow}>
          {[
            { id: "dark", label: "Dark Mode", icon: "moon-outline" },
            { id: "light", label: "Light Mode", icon: "sunny-outline" },
            { id: "system", label: "System", icon: "phone-portrait-outline" },
          ].map((item) => {
            const isSelected = mode === item.id;
            return (
              <TouchableOpacity
                key={item.id}
                onPress={() => setMode(item.id as any)}
                style={[
                  styles.themeChip,
                  {
                    backgroundColor: isSelected ? "rgba(7, 159, 189, 0.18)" : colors.surfaceElevated,
                    borderColor: isSelected ? colors.primary : colors.border,
                  },
                ]}
              >
                <Ionicons
                  name={item.icon as any}
                  size={18}
                  color={isSelected ? colors.primary : colors.textSecondary}
                />
                <Text
                  style={[
                    styles.themeChipText,
                    { color: isSelected ? colors.primary : colors.text },
                  ]}
                >
                  {item.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </Card>

      {/* Backend Server Configuration */}
      <Card style={styles.card}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>Backend Server URL</Text>
        <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
          Configure your local FastAPI server endpoint (use 10.0.2.2 for Android Emulator).
        </Text>

        <Input
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="http://10.0.2.2:8000"
          autoCapitalize="none"
          autoCorrect={false}
          leftIcon={<Ionicons name="server-outline" size={18} color={colors.textSecondary} />}
        />

        <Button
          title="Save & Test Connection"
          variant="outline"
          size="small"
          loading={testing}
          onPress={handleSaveAndTestUrl}
        />

        {connectionMessage && (
          <Text
            style={[
              styles.connectionMsg,
              {
                color: connectionMessage.includes("successfully")
                  ? colors.brandGreen
                  : colors.error,
              },
            ]}
          >
            {connectionMessage}
          </Text>
        )}
      </Card>

      {/* AI Model Status */}
      <Card style={styles.card}>
        <View style={styles.aiHeader}>
          <Text style={[styles.cardTitle, { color: colors.text, marginBottom: 0 }]}>
            Ollama AI Model
          </Text>
          <Badge
            label={aiStatus?.available ? "Online" : "Checking / Offline"}
            variant={aiStatus?.available ? "success" : "warning"}
          />
        </View>

        <Text style={[styles.aiModelName, { color: colors.primary }]}>
          Model: blaifa/InternVL3_5:4B
        </Text>

        <Text style={[styles.cardDesc, { color: colors.textSecondary, marginTop: 4 }]}>
          {aiStatus?.message || "Checks connectivity with local Ollama vision instance."}
        </Text>

        <Button
          title="Check Model Status"
          icon={<Ionicons name="refresh" size={14} color={colors.text} />}
          variant="secondary"
          size="small"
          loading={checkingAi}
          onPress={checkAiStatus}
          style={{ marginTop: 10 }}
        />
      </Card>

      {/* Data Retention & Privacy Policy (Section 23) */}
      <Card style={styles.card}>
        <View style={styles.aiHeader}>
          <Text style={[styles.cardTitle, { color: colors.text, marginBottom: 0 }]}>
            Data Integrity & Retention
          </Text>
          <Ionicons name="shield-checkmark-outline" size={18} color={colors.brandGreen} />
        </View>
        <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
          • Original handwritten answer sheet images: Retained on disk for 24 hours, then automatically purged per policy.
          {"\n"}• Question papers and official answer keys: Stored permanently as master examination records.
          {"\n"}• Transcripts, AI scores, teacher overrides, marks, and audit logs: Stored securely in the local SQLite database.
        </Text>
      </Card>

      <SchoolDetailsCard />

      <Card style={styles.card}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>Report Templates</Text>
        <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
          Choose and edit how reports and report cards look.
        </Text>
        <View style={{ flexDirection: "row", gap: 10 }}>
          <Button title="Exam report" icon={<Ionicons name="document-text-outline" size={16} color={colors.text} />}
            variant="secondary" size="small" style={{ flex: 1 }}
            onPress={() => (navigation as any)?.navigate?.("TemplateEditor", { kind: "report" })} />
          <Button title="Report card" icon={<Ionicons name="ribbon-outline" size={16} color={colors.text} />}
            variant="secondary" size="small" style={{ flex: 1 }}
            onPress={() => (navigation as any)?.navigate?.("TemplateEditor", { kind: "report_card" })} />
        </View>
      </Card>

      {/* System Diagnostics & Links */}
      <Card style={styles.card}>
        <Text style={[styles.cardTitle, { color: colors.text }]}>Academic Management</Text>
        <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
          Manage student rosters, classrooms, and subject modules.
        </Text>

        <View style={{ flexDirection: "row", gap: 10 }}>
          <Button
            title="Classes"
            icon={<Ionicons name="school-outline" size={16} color={colors.text} />}
            variant="secondary"
            size="small"
            style={{ flex: 1 }}
            onPress={() => (navigation as any)?.navigate?.("Classes")}
          />
          <Button
            title="Subjects"
            icon={<Ionicons name="book-outline" size={16} color={colors.text} />}
            variant="secondary"
            size="small"
            style={{ flex: 1 }}
            onPress={() => (navigation as any)?.navigate?.("Subjects")}
          />
          <Button
            title="Students"
            icon={<Ionicons name="people-outline" size={16} color={colors.text} />}
            variant="secondary"
            size="small"
            style={{ flex: 1 }}
            onPress={() => (navigation as any)?.navigate?.("Students")}
          />
        </View>
      </Card>

      {/* App Version Info */}
      <View style={{ alignItems: "center", marginVertical: 12 }}>
        <Text style={{ fontSize: 13, fontWeight: "700", color: colors.text }}>Eval AI Mobile v1.0.0</Text>
        <Text style={{ fontSize: 11, color: colors.textSecondary, marginTop: 2 }}>
          Smart Evaluation. Brighter Future.
        </Text>
      </View>

      {/* Sign Out Button */}
      <Button
        title="Sign Out"
        icon={<Ionicons name="log-out-outline" size={18} color="#FFFFFF" />}
        variant="danger"
        onPress={handleLogout}
        fullWidth
        style={{ marginTop: 4, marginBottom: 20 }}
      />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  card: {
    padding: 16,
    marginBottom: 14,
  },
  profileHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  avatar: {
    width: 54,
    height: 54,
    borderRadius: 27,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  nameText: {
    fontSize: 18,
    fontWeight: "700",
  },
  emailText: {
    fontSize: 13,
    marginTop: 2,
  },
  roleBadge: {
    fontSize: 11,
    fontWeight: "600",
    marginTop: 4,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 4,
  },
  cardDesc: {
    fontSize: 12,
    lineHeight: 16,
    marginBottom: 12,
  },
  themeOptionsRow: {
    flexDirection: "row",
    gap: 8,
  },
  themeChip: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
  },
  themeChipText: {
    fontSize: 12,
    fontWeight: "600",
  },
  connectionMsg: {
    fontSize: 12,
    marginTop: 8,
    textAlign: "center",
  },
  aiHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  aiModelName: {
    fontSize: 13,
    fontWeight: "700",
  },
});
