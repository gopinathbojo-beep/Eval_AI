import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api } from "../../api/client";
import type { Evaluation, Exam } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { SearchBar } from "../../components/SearchBar";
import { Pagination } from "../../components/Pagination";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { StatusBadge } from "../../components/Badge";
import { PenScore } from "../../components/PenScore";

interface EvaluationsQueueScreenProps {
  navigation: any;
}

const ITEMS_PER_PAGE = 8;

export const EvaluationsQueueScreen: React.FC<EvaluationsQueueScreenProps> = ({ navigation }) => {
  const { colors } = useTheme();

  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [exams, setExams] = useState<Exam[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters & Sorting
  const [search, setSearch] = useState("");
  const [selectedExamId, setSelectedExamId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const fetchData = useCallback(async () => {
    try {
      const [evalsRes, examsRes] = await Promise.all([
        api<Evaluation[]>("/evaluations"),
        api<Exam[]>("/exams"),
      ]);
      setEvaluations(evalsRes);
      setExams(examsRes);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load evaluations");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const hasRunning = evaluations.some((ev) => ev.run_status === "RUNNING");
    if (hasRunning) {
      const timer = setInterval(() => {
        fetchData();
      }, 2000);
      return () => clearInterval(timer);
    }
  }, [evaluations, fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const filteredData = useMemo(() => {
    let result = evaluations.filter((ev) => {
      const sName = ev.student?.name?.toLowerCase() || "";
      const sRoll = ev.student?.roll_number?.toLowerCase() || "";
      const eName = ev.exam_name?.toLowerCase() || "";
      const q = search.toLowerCase();

      const matchSearch = sName.includes(q) || sRoll.includes(q) || eName.includes(q);
      const matchExam = selectedExamId ? ev.exam_id === selectedExamId : true;
      const matchStatus = statusFilter ? ev.status === statusFilter : true;

      return matchSearch && matchExam && matchStatus;
    });

    result.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    return result;
  }, [evaluations, search, selectedExamId, statusFilter]);

  const totalPages = Math.ceil(filteredData.length / ITEMS_PER_PAGE) || 1;
  const paginatedData = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return filteredData.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredData, page]);

  const statusFilters = [
    { label: "All", value: null },
    { label: "Needs Review", value: "NEEDS_REVIEW" },
    { label: "Draft", value: "DRAFT" },
    { label: "Ready", value: "READY_FOR_EVALUATION" },
    { label: "Evaluating", value: "EVALUATING" },
    { label: "Finalized", value: "FINALIZED" },
  ];

  const pendingCount = evaluations.filter((e) => e.status !== "FINALIZED").length;
  const reviewCount = evaluations.filter((e) => e.status === "NEEDS_REVIEW" || e.status === "REVIEW_REQUIRED").length;

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      {/* Header Metric Bar */}
      <View style={[styles.headerBanner, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
        <View style={styles.metricItem}>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Queue Total</Text>
          <Text style={[styles.metricValue, { color: colors.primary }]}>{evaluations.length}</Text>
        </View>
        <View style={[styles.divider, { backgroundColor: colors.border }]} />
        <View style={styles.metricItem}>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Pending</Text>
          <Text style={[styles.metricValue, { color: colors.warning }]}>{pendingCount}</Text>
        </View>
        <View style={[styles.divider, { backgroundColor: colors.border }]} />
        <View style={styles.metricItem}>
          <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Needs Review</Text>
          <Text style={[styles.metricValue, { color: colors.error }]}>{reviewCount}</Text>
        </View>
      </View>

      {/* Search Bar */}
      <View style={styles.searchContainer}>
        <SearchBar
          value={search}
          onChangeText={(text) => {
            setSearch(text);
            setPage(1);
          }}
          placeholder="Search student, roll number, or exam..."
        />
      </View>

      {/* Status Filter Pills */}
      <View style={styles.filterScroll}>
        <FlatList
          horizontal
          showsHorizontalScrollIndicator={false}
          data={statusFilters}
          keyExtractor={(item) => item.label}
          contentContainerStyle={styles.filterContent}
          renderItem={({ item }) => {
            const active = statusFilter === item.value;
            return (
              <TouchableOpacity
                onPress={() => {
                  setStatusFilter(item.value);
                  setPage(1);
                }}
                style={[
                  styles.filterPill,
                  {
                    backgroundColor: active ? colors.primary : colors.surface,
                    borderColor: active ? colors.primary : colors.border,
                  },
                ]}
              >
                <Text
                  style={[
                    styles.filterPillText,
                    { color: active ? "#FFFFFF" : colors.textSecondary },
                  ]}
                >
                  {item.label}
                </Text>
              </TouchableOpacity>
            );
          }}
        />
      </View>

      {/* Evaluations Queue List */}
      {loading && !refreshing ? (
        <Loading message="Loading evaluation queue..." />
      ) : (
        <FlatList
          data={paginatedData}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor={colors.primary}
              colors={[colors.primary]}
            />
          }
          ListEmptyComponent={
            <Empty
              title="No evaluations in queue"
              description={
                search || statusFilter || selectedExamId
                  ? "No submissions matched your search filters."
                  : "Upload student answer sheets from the Exams tab to begin AI evaluation."
              }
              actionTitle={evaluations.length === 0 ? "Browse Exams" : undefined}
              onAction={() => navigation.navigate("ExamsTab")}
            />
          }
          renderItem={({ item }) => (
            <TouchableOpacity
              activeOpacity={0.8}
              onPress={() => navigation.navigate("EvaluationDetail", { evaluationId: item.id })}
            >
              <Card style={styles.evalCard}>
                <View style={styles.cardHeader}>
                  <View style={styles.studentInfo}>
                    <Text style={[styles.studentName, { color: colors.text }]}>
                      {item.student?.name || "Student Submission"}
                    </Text>
                    <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                      Roll No: {item.student?.roll_number} • Class: {item.student?.class_name || "Enrolled"}
                    </Text>
                    <Text style={[styles.examText, { color: colors.primary }]}>
                      Exam: {item.exam_name || "Examination"}
                    </Text>
                  </View>
                  <PenScore
                    score={item.total_marks}
                    maxScore={item.maximum_marks}
                    size="small"
                  />
                </View>

                <View style={[styles.cardFooter, { borderTopColor: colors.border }]}>
                  <View style={styles.badgeRow}>
                    <StatusBadge status={item.run_status === "RUNNING" ? "EVALUATING" : item.status} />
                    {item.percentage !== null && item.percentage !== undefined && (
                      <Text style={[styles.percentageText, { color: colors.brandGreen }]}>
                        {item.percentage.toFixed(1)}%
                      </Text>
                    )}
                  </View>

                  <View style={styles.actionBtnRow}>
                    <Text style={[styles.reviewActionText, { color: colors.primary }]}>
                      {item.status === "FINALIZED"
                        ? "View Final Result"
                        : item.run_status === "RUNNING"
                        ? "Evaluating..."
                        : "Review & Approve"}
                    </Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.primary} />
                  </View>
                </View>
              </Card>
            </TouchableOpacity>
          )}
          ListFooterComponent={
            totalPages > 1 ? (
              <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} />
            ) : null
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  headerBanner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  metricItem: {
    alignItems: "center",
  },
  metricLabel: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  metricValue: {
    fontSize: 18,
    fontWeight: "800",
    marginTop: 2,
  },
  divider: {
    width: 1,
    height: 24,
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  filterScroll: {
    paddingVertical: 8,
  },
  filterContent: {
    paddingHorizontal: 16,
    gap: 8,
  },
  filterPill: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
  },
  filterPillText: {
    fontSize: 12,
    fontWeight: "600",
  },
  listContent: {
    padding: 16,
    gap: 12,
    paddingBottom: 32,
  },
  evalCard: {
    padding: 14,
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  studentInfo: {
    flex: 1,
    marginRight: 10,
  },
  studentName: {
    fontSize: 16,
    fontWeight: "700",
  },
  metaText: {
    fontSize: 12,
    marginTop: 2,
  },
  examText: {
    fontSize: 12,
    fontWeight: "600",
    marginTop: 3,
  },
  cardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderTopWidth: 1,
    marginTop: 12,
    paddingTop: 10,
  },
  badgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  percentageText: {
    fontSize: 14,
    fontWeight: "700",
  },
  actionBtnRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  reviewActionText: {
    fontSize: 13,
    fontWeight: "600",
  },
});
