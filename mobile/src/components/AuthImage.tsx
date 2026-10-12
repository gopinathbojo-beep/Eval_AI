import React, { useState, useEffect } from "react";
import { Image, View, ActivityIndicator, StyleSheet, ImageStyle, Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { getBaseUrl, getToken } from "../api/client";
import { useTheme } from "../theme/ThemeContext";

interface AuthImageProps {
  path: string;
  style?: ImageStyle;
  resizeMode?: "contain" | "cover" | "stretch";
}

export const AuthImage: React.FC<AuthImageProps> = ({
  path,
  style,
  resizeMode = "contain",
}) => {
  const { colors } = useTheme();
  const [sourceUri, setSourceUri] = useState<string | null>(null);
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const [base64Uri, setBase64Uri] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setLoading(true);
        setError(false);
        setBase64Uri(null);
        const [baseUrl, token] = await Promise.all([getBaseUrl(), getToken()]);
        const cleanPath = path.startsWith("/") ? path : `/${path}`;
        const fullUrl = `${baseUrl}/api${cleanPath}`;
        const sep = fullUrl.includes("?") ? "&" : "?";
        // Embed token into URL query so native Android Fresco/OkHttp passes authentication reliably
        const authenticatedUrl = token
          ? `${fullUrl}${sep}token=${encodeURIComponent(token)}`
          : fullUrl;

        if (active) {
          setSourceUri(authenticatedUrl);
          setHeaders(token ? { Authorization: `Bearer ${token}` } : {});
        }
      } catch (e) {
        console.warn("AuthImage init error:", e);
        if (active) setError(true);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [path, retryCount]);

  const handleNativeImageError = async () => {
    // If native Image tag failed (common with Fresco header drops on Android), fetch directly with fetch()
    if (sourceUri && !base64Uri) {
      try {
        const token = await getToken();
        const res = await fetch(sourceUri, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const blob = await res.blob();
          const reader = new FileReader();
          reader.onloadend = () => {
            if (typeof reader.result === "string") {
              setBase64Uri(reader.result);
              setError(false);
            } else {
              setError(true);
            }
          };
          reader.readAsDataURL(blob);
          return;
        }
      } catch (err) {
        console.warn("AuthImage fallback fetch failed:", err);
      }
    }
    setError(true);
  };

  if (loading) {
    return (
      <View style={[styles.placeholder, { backgroundColor: colors.surfaceElevated }, style]}>
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  }

  if (error || (!sourceUri && !base64Uri)) {
    return (
      <TouchableOpacity
        onPress={() => setRetryCount((c) => c + 1)}
        activeOpacity={0.7}
        style={[styles.placeholder, { backgroundColor: colors.surfaceElevated, borderColor: colors.border, borderWidth: 1 }, style]}
      >
        <Ionicons name="refresh-outline" size={16} color={colors.textSecondary} style={{ marginBottom: 4 }} />
        <Text style={[styles.errorText, { color: colors.textSecondary }]}>Preview unavailable • Tap to retry</Text>
      </TouchableOpacity>
    );
  }

  return (
    <Image
      source={base64Uri ? { uri: base64Uri } : { uri: sourceUri!, headers }}
      style={[styles.image, style]}
      resizeMode={resizeMode}
      onError={handleNativeImageError}
    />
  );
};

const styles = StyleSheet.create({
  placeholder: {
    minHeight: 120,
    width: "100%",
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  image: {
    minHeight: 120,
    width: "100%",
    borderRadius: 8,
  },
  errorText: {
    fontSize: 12,
  },
});
