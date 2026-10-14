import React from "react";
import { Platform } from "react-native";
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
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomInset = Math.max(insets.bottom, Platform.OS === "android" ? 8 : 6);
  const tabHeight = 54 + bottomInset;

  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: {
          backgroundColor: colors.surface,
          shadowColor: "transparent",
          elevation: 0,
        },
        headerTitleStyle: {
          color: colors.text,
          fontWeight: "800",
          fontSize: 18,
          letterSpacing: 0.5,
        },
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: 1,
          height: tabHeight,
          paddingBottom: bottomInset,
          paddingTop: 6,
        },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.tabBarInactive,
        tabBarLabelStyle: {
          fontSize: 10,
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
          headerTitle: "ADEM",
          tabBarLabel: "Dashboard",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="grid-outline" size={size - 2} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="ExamsTab"
        component={ExamsListScreen}
        options={{
          title: "Examinations",
          tabBarLabel: "Exams",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="document-text-outline" size={size - 2} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="CreateExamTab"
        component={ExamCreateScreen}
        options={{
          title: "Create Examination",
          tabBarLabel: "Create",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="add-circle-outline" size={size} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="EvaluationsTab"
        component={EvaluationsQueueScreen}
        options={{
          title: "Evaluation Queue",
          tabBarLabel: "Evaluate",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="checkbox-outline" size={size - 2} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="ResultsTab"
        component={ResultsListScreen}
        options={{
          title: "Results & Marksheets",
          tabBarLabel: "Results",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="ribbon-outline" size={size - 2} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
};
