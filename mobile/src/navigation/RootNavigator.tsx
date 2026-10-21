import React from "react";
import { View, ActivityIndicator } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../theme/ThemeContext";

// Screens
import { LoginScreen } from "../screens/auth/LoginScreen";
import { AppTabs } from "./AppTabs";
import { ExamCreateScreen } from "../screens/exams/ExamCreateScreen";
import { ExamWorkspaceScreen } from "../screens/exams/ExamWorkspaceScreen";
import { EvaluationDetailScreen } from "../screens/evaluations/EvaluationDetailScreen";
import { ResultDetailScreen } from "../screens/results/ResultDetailScreen";
import { ClassesScreen } from "../screens/classes/ClassesScreen";
import { SubjectsScreen } from "../screens/subjects/SubjectsScreen";
import { StudentsScreen } from "../screens/students/StudentsScreen";
import { VerifyExamScreen } from "../screens/exams/VerifyExamScreen";
import { SettingsScreen } from "../screens/settings/SettingsScreen";
import { TemplateEditorScreen } from "../screens/settings/TemplateEditorScreen";

const Stack = createNativeStackNavigator();

export const RootNavigator: React.FC = () => {
  const { isAuthenticated, loading } = useAuth();
  const { colors, isDark } = useTheme();

  if (loading) {
    return (
      <View
        style={{
          flex: 1,
          justifyContent: "center",
          alignItems: "center",
          backgroundColor: colors.background,
        }}
      >
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerStyle: {
            backgroundColor: colors.surface,
          },
          headerShadowVisible: false,
          headerTintColor: colors.primary,
          headerTitleStyle: {
            color: colors.text,
            fontWeight: "700",
            fontSize: 17,
          },
          contentStyle: {
            backgroundColor: colors.background,
          },
        }}
      >
        {!isAuthenticated ? (
          <Stack.Screen
            name="Login"
            component={LoginScreen}
            options={{ headerShown: false }}
          />
        ) : (
          <>
            <Stack.Screen
              name="MainTabs"
              component={AppTabs}
              options={{ headerShown: false }}
            />
            <Stack.Screen
              name="ExamCreate"
              component={ExamCreateScreen}
              options={{ title: "New Examination" }}
            />
            <Stack.Screen
              name="ExamWorkspace"
              component={ExamWorkspaceScreen}
              options={{ title: "Exam Workspace" }}
            />
            <Stack.Screen
              name="VerifyExam"
              component={VerifyExamScreen}
              options={{ title: "Verify Examination" }}
            />
            <Stack.Screen
              name="EvaluationDetail"
              component={EvaluationDetailScreen}
              options={{ title: "Evaluation Review" }}
            />
            <Stack.Screen
              name="ResultDetail"
              component={ResultDetailScreen}
              options={{ title: "Result Marksheet" }}
            />
            <Stack.Screen
              name="Classes"
              component={ClassesScreen}
              options={{ title: "Classrooms & Grades" }}
            />
            <Stack.Screen
              name="Subjects"
              component={SubjectsScreen}
              options={{ title: "Curriculum Subjects" }}
            />
            <Stack.Screen
              name="Students"
              component={StudentsScreen}
              options={{ title: "Students" }}
            />
            <Stack.Screen
              name="Settings"
              component={SettingsScreen}
              options={{ title: "Settings & AI Diagnostics" }}
            />
            <Stack.Screen
              name="TemplateEditor"
              component={TemplateEditorScreen}
              options={{ title: "Report Template" }}
            />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
};
