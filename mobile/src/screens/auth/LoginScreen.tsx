import React, { useState, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../theme/ThemeContext";
import { Logo } from "../../components/Logo";
import { Input } from "../../components/Input";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import {
  getBaseUrl,
  setBaseUrl,
  getDefaultBackendUrl,
  resetToDefaultUrl,
} from "../../api/client";

export const LoginScreen: React.FC = () => {
  const { login } = useAuth();
  const { colors } = useTheme();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [serverUrl, setServerUrlState] = useState("");
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<string | null>(null);

  useEffect(() => {
    getBaseUrl().then((url) => {
      setServerUrlState(url);
    });
  }, []);

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert("Required Fields", "Please enter your email and password.");
      return;
    }

    try {
      setLoading(true);
      if (serverUrl.trim()) {
        await setBaseUrl(serverUrl.trim());
      }
      await login(email.trim(), password);
    } catch (err: any) {
      Alert.alert(
        "Login Failed",
        err.message ||
          "Could not connect to the backend server. Tap 'Configure Backend Server URL' below to check the connection."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      setTestingConnection(true);
      setConnectionStatus(null);
      const cleanUrl = serverUrl.trim().replace(/\/+$/, "");
      await setBaseUrl(cleanUrl);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000);

      const res = await fetch(`${cleanUrl}/api/health`, {
        method: "GET",
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        setConnectionStatus("Connected successfully to ADEM backend!");
      } else {
        setConnectionStatus(`Connected, but server returned HTTP ${res.status}.`);
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        setConnectionStatus(`Timed out reaching ${serverUrl}. Check Wi-Fi and firewall.`);
      } else {
        setConnectionStatus(`Cannot reach ${serverUrl}. Check IP/port and firewall.`);
      }
    } finally {
      setTestingConnection(false);
    }
  };

  const handleAutoDetect = async () => {
    const url = await resetToDefaultUrl();
    setServerUrlState(url);
    Alert.alert("Auto-Detected URL", `Backend address set to:\n${url}`);
  };

  const fillTeacherCredentials = () => {
    setEmail("teacher@school.org");
    setPassword("teacher123");
  };

  const fillYouSchoolCredentials = () => {
    setEmail("you@school.org");
    setPassword("a-strong-password");
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: colors.background }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.header}>
          <Logo size="large" showSubtitle />
          <Text style={[styles.welcomeText, { color: colors.textSecondary }]}>
            Smart Evaluation. Brighter Future.
          </Text>
        </View>

        <Card style={styles.formCard}>
          <Text style={[styles.title, { color: colors.text }]}>Sign In</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Access your teacher dashboard and examination workspace
          </Text>

          <Input
            label="Email Address"
            placeholder="teacher@school.org"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            leftIcon={
              <Ionicons name="mail-outline" size={18} color={colors.textSecondary} />
            }
          />

          <Input
            label="Password"
            placeholder="Enter your password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!showPassword}
            leftIcon={
              <Ionicons name="lock-closed-outline" size={18} color={colors.textSecondary} />
            }
            rightIcon={
              <TouchableOpacity
                onPress={() => setShowPassword(!showPassword)}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              >
                <Ionicons
                  name={showPassword ? "eye-off-outline" : "eye-outline"}
                  size={18}
                  color={colors.textSecondary}
                />
              </TouchableOpacity>
            }
          />

          <Button
            title="Sign In to ADEM"
            onPress={handleLogin}
            variant="gradient"
            loading={loading}
            fullWidth
            style={styles.signInButton}
          />

          <View style={{ flexDirection: "row", gap: 8, marginTop: 8 }}>
            <Button
              title="Fill teacher@school.org"
              onPress={fillTeacherCredentials}
              variant="ghost"
              size="small"
              style={{ flex: 1 }}
            />
            <Button
              title="Fill you@school.org"
              onPress={fillYouSchoolCredentials}
              variant="ghost"
              size="small"
              style={{ flex: 1 }}
            />
          </View>

          {/* Current Server Indicator */}
          <TouchableOpacity
            style={styles.serverToggle}
            onPress={() => setShowServerConfig(!showServerConfig)}
          >
            <Ionicons
              name="server-outline"
              size={14}
              color={colors.textSecondary}
              style={{ marginRight: 6 }}
            />
            <Text style={[styles.serverToggleText, { color: colors.textSecondary }]}>
              Server: <Text style={{ color: colors.primary, fontWeight: "600" }}>{serverUrl || "Detecting..."}</Text>
            </Text>
            <Ionicons
              name={showServerConfig ? "chevron-up" : "chevron-down"}
              size={14}
              color={colors.textSecondary}
              style={{ marginLeft: 4 }}
            />
          </TouchableOpacity>

          {showServerConfig && (
            <View style={[styles.serverBox, { borderColor: colors.border }]}>
              <Input
                label="Backend API Base URL"
                value={serverUrl}
                onChangeText={setServerUrlState}
                placeholder="http://10.195.96.202:8000"
                autoCapitalize="none"
                helper="Use your PC's Wi-Fi IP for physical phones or http://10.0.2.2:8000 for Android emulator."
              />

              {/* Quick Preset Buttons */}
              <View style={{ flexDirection: "row", gap: 6, marginBottom: 8 }}>
                <TouchableOpacity
                  onPress={() => setServerUrlState("http://10.195.96.202:8000")}
                  style={[styles.presetChip, { borderColor: colors.border, backgroundColor: colors.surfaceElevated }]}
                >
                  <Text style={[styles.presetChipText, { color: colors.primary }]}>PC Wi-Fi (10.195.96.202)</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setServerUrlState("http://10.0.2.2:8000")}
                  style={[styles.presetChip, { borderColor: colors.border, backgroundColor: colors.surfaceElevated }]}
                >
                  <Text style={[styles.presetChipText, { color: colors.primary }]}>Emulator (10.0.2.2)</Text>
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: "row", gap: 8, marginTop: 4 }}>
                <Button
                  title="Test Connection"
                  onPress={handleTestConnection}
                  variant="outline"
                  size="small"
                  loading={testingConnection}
                  style={{ flex: 1 }}
                />
                <Button
                  title="Auto-Detect IP"
                  onPress={handleAutoDetect}
                  variant="secondary"
                  size="small"
                  style={{ flex: 1 }}
                />
              </View>

              {connectionStatus && (
                <Text
                  style={[
                    styles.connectionStatus,
                    {
                      color: connectionStatus.includes("successfully")
                        ? colors.brandGreen
                        : colors.error,
                    },
                  ]}
                >
                  {connectionStatus}
                </Text>
              )}
            </View>
          )}
        </Card>

        <View style={styles.footer}>
          <Text style={[styles.footerText, { color: colors.textSecondary }]}>
            ADEM System • Powered by Ollama blaifa/InternVL3_5:4B
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: "center",
    padding: 24,
  },
  header: {
    alignItems: "center",
    marginBottom: 28,
  },
  welcomeText: {
    fontSize: 13,
    marginTop: 8,
    textAlign: "center",
    letterSpacing: 0.3,
  },
  formCard: {
    padding: 24,
    borderRadius: 20,
  },
  title: {
    fontSize: 22,
    fontWeight: "700",
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    marginBottom: 20,
  },
  signInButton: {
    marginTop: 8,
  },
  serverToggle: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 18,
    paddingVertical: 6,
  },
  serverToggleText: {
    fontSize: 12,
    fontWeight: "500",
  },
  serverBox: {
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
  },
  connectionStatus: {
    fontSize: 12,
    marginTop: 8,
    textAlign: "center",
  },
  presetChip: {
    flex: 1,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderRadius: 6,
    borderWidth: 1,
    alignItems: "center",
  },
  presetChipText: {
    fontSize: 11,
    fontWeight: "600",
  },
  footer: {
    marginTop: 24,
    alignItems: "center",
  },
  footerText: {
    fontSize: 11,
    textAlign: "center",
  },
});
