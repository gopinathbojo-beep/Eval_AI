import React from "react";
import { Platform, View, Text, StyleSheet } from "react-native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../theme/ThemeContext";

import { DashboardScreen } from "../screens/dashboard/DashboardScreen";
import { ExamsListScreen } from "../screens/exams/ExamsListScreen";
import { ExamCreateScreen } from "../screens/exams/ExamCreateScreen";
import { EvaluationsQueueScreen } from "../screens/evaluations/EvaluationsQueueScreen";
import { ResultsListScreen } from "../screens/results/ResultsListScreen";

const Tab = createBottomTabNavigator();

export const AppTabs: React.FC = () => {
  const { colors, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomInset = Math.max(insets.bottom, Platform.OS === "android" ? 8 : 6);
  const tabHeight = 56 + bottomInset;

  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: {
          backgroundColor: colors.surface,
          shadowColor: "transparent",
          elevation: 0,
          borderBottomWidth: 1,
          borderBottomColor: colors.border,
        },
        headerTitleStyle: {
          color: colors.text,
          fontWeight: "800",
          fontSize: 18,
          letterSpacing: 0.3,
        },
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          height: tabHeight,
          paddingBottom: bottomInset,
          paddingTop: 6,
          ...Platform.select({
            ios: {
              shadowColor: "#000",
              shadowOffset: { width: 0, height: -2 },
              shadowOpacity: isDark ? 0.2 : 0.03,
              shadowRadius: 4,
            },
            android: {
              elevation: 4,
            },
          }),
        },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.tabBarInactive,
        tabBarLabelStyle: {
          fontSize: 11,
          fontWeight: "600",
          marginTop: -2,
        },
        tabBarItemStyle: {
          paddingVertical: 2,
        },
      }}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{
          headerTitle: () => (
            <View style={styles.headerTitleRow}>
              <View style={[styles.headerCrest, { backgroundColor: colors.primary }]}>
                <Ionicons name="school" size={14} color="#FFFFFF" />
              </View>
              <Text style={[styles.headerTitleText, { color: colors.text }]}>Eval AI</Text>
            </View>
          ),
          tabBarLabel: "Dashboard",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons
              name={focused ? "grid" : "grid-outline"}
              size={size - 2}
              color={color}
            />
          ),
        }}
      />
      <Tab.Screen
        name="ExamsTab"
        component={ExamsListScreen}
        options={{
          title: "Examinations",
          tabBarLabel: "Exams",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons
              name={focused ? "document-text" : "document-text-outline"}
              size={size - 2}
              color={color}
            />
          ),
        }}
      />
      <Tab.Screen
        name="CreateExamTab"
        component={ExamCreateScreen}
        options={{
          title: "New Examination",
          tabBarLabel: "Create",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons
              name={focused ? "add-circle" : "add-circle-outline"}
              size={size + 1}
              color={color}
            />
          ),
        }}
      />
      <Tab.Screen
        name="EvaluationsTab"
        component={EvaluationsQueueScreen}
        options={{
          title: "Evaluation Queue",
          tabBarLabel: "Evaluate",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons
              name={focused ? "checkbox" : "checkbox-outline"}
              size={size - 2}
              color={color}
            />
          ),
        }}
      />
      <Tab.Screen
        name="ResultsTab"
        component={ResultsListScreen}
        options={{
          title: "Finalized Results",
          tabBarLabel: "Results",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons
              name={focused ? "ribbon" : "ribbon-outline"}
              size={size - 2}
              color={color}
            />
          ),
        }}
      />
    </Tab.Navigator>
  );
};

const styles = StyleSheet.create({
  headerTitleRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  headerCrest: {
    width: 24,
    height: 24,
    borderRadius: 6,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 8,
  },
  headerTitleText: {
    fontSize: 18,
    fontWeight: "800",
    letterSpacing: 0.3,
  },
});
