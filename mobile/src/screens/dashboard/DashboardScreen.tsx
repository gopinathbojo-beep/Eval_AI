import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../theme/ThemeContext";
import { api } from "../../api/client";
import type { Dashboard, Exam, Evaluation } from "../../types";
import { Card } from "../../components/Card";
import { StatusBadge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { PenScore } from "../../components/PenScore";

interface DashboardScreenProps {
  navigation: any;
}

export const DashboardScreen: React.FC<DashboardScreenProps> = ({ navigation }) => {
  const { teacher } = useAuth();
  const { colors, isDark } = useTheme();

  const [data, setData] = useState<Dashboard | null>(null);
  const [aiStatus, setAiStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      setError(null);
      const [res, aiRes] = await Promise.all([
        api<Dashboard>("/dashboard"),
        api<any>("/system/ai-status").catch(() => ({ available: false, message: "AI Service Offline" })),
      ]);
      setData(res);
      setAiStatus(aiRes);
    } catch (err: any) {
      setError(err.message || "Failed to load dashboard data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchDashboard();
  };

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading examination dashboard..." />
      </View>
    );
  }

  const statItems = [
    { label: "Classes", count: data?.total_classes ?? 0, icon: "school-outline", color: colors.primary, tab: "Classes" },
    { label: "Subjects", count: data?.total_subjects ?? 0, icon: "book-outline", color: colors.secondary, tab: "Subjects" },
    { label: "Exams", count: data?.total_exams ?? 0, icon: "document-text-outline", color: colors.primary, tab: "ExamsTab" },
    { label: "Students", count: data?.total_students ?? 0, icon: "people-outline", color: colors.secondary, tab: "Students" },
    { label: "Pending Evals", count: data?.pending_evaluations ?? 0, icon: "time-outline", color: colors.warning, tab: "EvaluationsTab" },
    { label: "Finalized", count: data?.completed_evaluations ?? 0, icon: "checkmark-done-circle-outline", color: colors.brandGreen, tab: "ResultsTab" },
  ];

  const firstIncompleteExam = data?.recent_exams?.find((e: Exam) => e.status !== "FINALIZED");

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.background }]}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor={colors.primary}
          colors={[colors.primary]}
        />
      }
    >
      {/* Welcome Banner */}
      <View style={styles.header}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
          <View style={{ flex: 1 }}>
            <Text style={[styles.welcomeGreeting, { color: colors.textSecondary }]}>
              Welcome back,
            </Text>
            <Text style={[styles.teacherName, { color: colors.text }]}>
              {teacher?.name || "Teacher"}
            </Text>
            <Text style={[styles.schoolSubtitle, { color: colors.primary }]}>
              Eval AI • Academic Evaluation Platform
            </Text>
          </View>

          <TouchableOpacity
            style={[styles.settingsIconBtn, { backgroundColor: colors.surface, borderColor: colors.border }]}
            onPress={() => navigation.navigate("Settings")}
            accessibilityLabel="Open settings"
          >
            <Ionicons name="settings-outline" size={20} color={colors.text} />
          </TouchableOpacity>
        </View>

        {/* AI & Backend Status Pill Banner */}
        <View
          style={[
            styles.aiStatusBanner,
            {
              backgroundColor: aiStatus?.available ? colors.successSoft : colors.warningSoft,
              borderColor: aiStatus?.available ? "rgba(22, 163, 74, 0.3)" : "rgba(217, 119, 6, 0.3)",
            },
          ]}
        >
          <Ionicons
            name={aiStatus?.available ? "checkmark-circle" : "alert-circle"}
            size={16}
            color={aiStatus?.available ? colors.success : colors.warning}
          />
          <Text
            style={[
              styles.aiStatusText,
              { color: aiStatus?.available ? colors.success : colors.warning },
            ]}
          >
            {aiStatus?.available
              ? "Local AI Model Connected (InternVL 4B)"
              : "AI Model Offline — Check Local Service"}
          </Text>
        </View>
      </View>

      {/* Quick Action Buttons */}
      <View style={styles.quickActions}>
        <Button
          title="Create Exam"
          icon={<Ionicons name="add" size={18} color="#FFFFFF" />}
          variant="primary"
          size="small"
          onPress={() => navigation.navigate("ExamCreate")}
          style={{ flex: 1 }}
        />
        {firstIncompleteExam && (
          <Button
            title="Setup Paper"
            icon={<Ionicons name="arrow-forward-circle-outline" size={16} color={colors.text} />}
            variant="secondary"
            size="small"
            onPress={() => navigation.navigate("ExamWorkspace", { examId: firstIncompleteExam.id })}
            style={{ flex: 1 }}
          />
        )}
        <Button
          title="Review Queue"
          icon={<Ionicons name="checkbox-outline" size={16} color={colors.text} />}
          variant="secondary"
          size="small"
          onPress={() => navigation.navigate("EvaluationsTab")}
          style={{ flex: 1 }}
        />
      </View>

      {/* Statistics Grid */}
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Evaluation Overview</Text>
      <View style={styles.statsGrid}>
        {statItems.map((item, index) => (
          <TouchableOpacity
            key={index}
            style={styles.statCardWrapper}
            activeOpacity={0.8}
            onPress={() => {
              if (item.tab) navigation.navigate(item.tab);
            }}
          >
            <Card style={styles.statCard}>
              <View style={styles.statHeader}>
                <View
                  style={[
                    styles.iconBox,
                    { backgroundColor: `${item.color}15`, borderColor: `${item.color}30` },
                  ]}
                >
                  <Ionicons name={item.icon as any} size={18} color={item.color} />
                </View>
                <Text style={[styles.statCount, { color: colors.text }]}>
                  {item.count}
                </Text>
              </View>
              <Text style={[styles.statLabel, { color: colors.textSecondary }]}>
                {item.label}
              </Text>
            </Card>
          </TouchableOpacity>
        ))}
      </View>

      {/* Recent Exams Section */}
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Recent Examinations</Text>
        <TouchableOpacity onPress={() => navigation.navigate("ExamsTab")}>
          <Text style={[styles.viewAllText, { color: colors.primary }]}>View All &rarr;</Text>
        </TouchableOpacity>
      </View>

      {(!data?.recent_exams || data.recent_exams.length === 0) ? (
        <Empty
          title="No exams created yet"
          description="Create your first examination to upload question papers and evaluate student answer sheets."
          actionTitle="Create Exam"
          onAction={() => navigation.navigate("ExamCreate")}
        />
      ) : (
        data.recent_exams.map((exam: Exam) => (
          <TouchableOpacity
            key={exam.id}
            activeOpacity={0.82}
            onPress={() => navigation.navigate("ExamWorkspace", { examId: exam.id })}
          >
            <Card style={styles.examCard}>
              <View style={styles.examCardHeader}>
                <View style={{ flex: 1, paddingRight: 8 }}>
                  <Text style={[styles.examName, { color: colors.text }]}>
                    {exam.name}
                  </Text>
                  <Text style={[styles.examMeta, { color: colors.textSecondary }]}>
                    {exam.class_name} • {exam.subject_name} ({exam.academic_year || "Current Year"})
                  </Text>
                </View>
                <StatusBadge status={exam.status} size="small" />
              </View>
              <View style={[styles.examFooter, { borderTopColor: colors.border }]}>
                <Text style={[styles.examDetailText, { color: colors.textSecondary }]}>
                  Total Marks: <Text style={{ color: colors.text, fontWeight: "700" }}>{exam.total_marks}</Text>
                </Text>
                <View style={styles.cardArrowRow}>
                  <Text style={[styles.openActionText, { color: colors.primary }]}>Workspace</Text>
                  <Ionicons name="chevron-forward" size={15} color={colors.primary} />
                </View>
              </View>
            </Card>
          </TouchableOpacity>
        ))
      )}

      {/* Recent Evaluations Section */}
      <View style={[styles.sectionHeader, { marginTop: 20 }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Recent Evaluations</Text>
        <TouchableOpacity onPress={() => navigation.navigate("ResultsTab")}>
          <Text style={[styles.viewAllText, { color: colors.primary }]}>View All &rarr;</Text>
        </TouchableOpacity>
      </View>

      {(!data?.recent_evaluations || data.recent_evaluations.length === 0) ? (
        <Empty
          title="No evaluations yet"
          description="Uploaded student answer sheets will appear here once processed."
        />
      ) : (
        data.recent_evaluations.map((ev: Evaluation) => (
          <TouchableOpacity
            key={ev.id}
            activeOpacity={0.82}
            onPress={() => navigation.navigate("EvaluationDetail", { evaluationId: ev.id })}
          >
            <Card style={styles.evalCard}>
              <View style={styles.evalCardHeader}>
                <View style={{ flex: 1, paddingRight: 8 }}>
                  <Text style={[styles.evalStudentName, { color: colors.text }]}>
                    {ev.student?.name || "Student"}
                  </Text>
                  <Text style={[styles.evalMeta, { color: colors.textSecondary }]}>
                    Roll: {ev.student?.roll_number} • {ev.exam_name || "Exam"}
                  </Text>
                </View>
                <PenScore
                  score={ev.total_marks}
                  maxScore={ev.maximum_marks}
                  size="small"
                />
              </View>
              <View style={[styles.evalFooter, { borderTopColor: colors.border }]}>
                <StatusBadge status={ev.status} size="small" />
                {ev.percentage !== null && ev.percentage !== undefined && (
                  <Text style={[styles.percentageText, { color: colors.brandGreen }]}>
                    {ev.percentage.toFixed(1)}%
                  </Text>
                )}
              </View>
            </Card>
          </TouchableOpacity>
        ))
      )}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 32,
  },
  header: {
    marginBottom: 16,
  },
  welcomeGreeting: {
    fontSize: 13,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  teacherName: {
    fontSize: 22,
    fontWeight: "800",
    marginTop: 2,
    letterSpacing: 0.2,
  },
  schoolSubtitle: {
    fontSize: 12,
    fontWeight: "600",
    marginTop: 2,
  },
  quickActions: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 20,
  },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "800",
    letterSpacing: 0.2,
    marginBottom: 10,
  },
  viewAllText: {
    fontSize: 13,
    fontWeight: "700",
  },
  statsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginHorizontal: -4,
    marginBottom: 16,
  },
  statCardWrapper: {
    width: "33.33%",
    paddingHorizontal: 4,
    marginBottom: 8,
  },
  statCard: {
    padding: 12,
    marginBottom: 0,
  },
  statHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  iconBox: {
    width: 32,
    height: 32,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  statCount: {
    fontSize: 18,
    fontWeight: "800",
  },
  statLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  examCard: {
    marginBottom: 10,
    padding: 14,
  },
  examCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  examName: {
    fontSize: 15,
    fontWeight: "700",
  },
  examMeta: {
    fontSize: 12,
    marginTop: 3,
  },
  examFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
  },
  examDetailText: {
    fontSize: 12,
  },
  cardArrowRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
  },
  openActionText: {
    fontSize: 12,
    fontWeight: "600",
  },
  evalCard: {
    marginBottom: 10,
    padding: 14,
  },
  evalCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  evalStudentName: {
    fontSize: 15,
    fontWeight: "700",
  },
  evalMeta: {
    fontSize: 12,
    marginTop: 3,
  },
  evalFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
  },
  percentageText: {
    fontSize: 13,
    fontWeight: "700",
  },
  settingsIconBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  aiStatusBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 10,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    borderWidth: 1,
  },
  aiStatusText: {
    fontSize: 12,
    fontWeight: "700",
  },
});
