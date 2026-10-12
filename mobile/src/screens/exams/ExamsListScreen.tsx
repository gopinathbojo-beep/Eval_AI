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
import type { Exam, ClassRow, Subject } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { SearchBar } from "../../components/SearchBar";
import { Pagination } from "../../components/Pagination";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { StatusBadge } from "../../components/Badge";

interface ExamsListScreenProps {
  navigation: any;
}

const ITEMS_PER_PAGE = 8;

export const ExamsListScreen: React.FC<ExamsListScreenProps> = ({ navigation }) => {
  const { colors } = useTheme();

  const [exams, setExams] = useState<Exam[]>([]);
  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters & Sorting
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [classFilter, setClassFilter] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const fetchData = useCallback(async () => {
    try {
      const [examsRes, classesRes, subjectsRes] = await Promise.all([
        api<Exam[]>("/exams"),
        api<ClassRow[]>("/classes"),
        api<Subject[]>("/subjects"),
      ]);
      setExams(examsRes);
      setClasses(classesRes);
      setSubjects(subjectsRes);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load examinations");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const toggleSort = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  const filteredAndSorted = useMemo(() => {
    let result = exams.filter((e) => {
      const matchSearch =
        e.name.toLowerCase().includes(search.toLowerCase()) ||
        e.subject_name.toLowerCase().includes(search.toLowerCase()) ||
        e.class_name.toLowerCase().includes(search.toLowerCase());
      const matchStatus = statusFilter ? e.status === statusFilter : true;
      const matchClass = classFilter ? e.class_id === classFilter : true;
      return matchSearch && matchStatus && matchClass;
    });

    result.sort((a, b) => {
      const timeA = new Date(a.created_at).getTime();
      const timeB = new Date(b.created_at).getTime();
      return sortOrder === "asc" ? timeA - timeB : timeB - timeA;
    });

    return result;
  }, [exams, search, statusFilter, classFilter, sortOrder]);

  const totalPages = Math.ceil(filteredAndSorted.length / ITEMS_PER_PAGE) || 1;
  const paginatedData = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return filteredAndSorted.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredAndSorted, page]);

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, classFilter, sortOrder]);

  const handleDeleteExam = (exam: Exam) => {
    Alert.alert(
      "Delete Exam",
      `Are you sure you want to delete "${exam.name}"? All associated papers and evaluations will be permanently removed.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              await api(`/exams/${exam.id}`, { method: "DELETE" });
              fetchData();
            } catch (err: any) {
              Alert.alert("Error", err.message || "Failed to delete exam");
            }
          },
        },
      ]
    );
  };

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading examinations..." />
      </View>
    );
  }

  const statuses = ["ALL", "DRAFT", "QUESTIONS_VERIFIED", "READY_FOR_EVALUATION", "FINALIZED"];

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.topBar}>
        <SearchBar
          value={search}
          onChangeText={setSearch}
          placeholder="Search exams, subjects, classes..."
          onSortPress={toggleSort}
          sortDirection={sortOrder}
        />

        {/* Filter status row */}
        <View style={styles.filterBar}>
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={statuses}
            keyExtractor={(item) => item}
            contentContainerStyle={styles.statusChips}
            renderItem={({ item }) => {
              const isSelected = item === "ALL" ? statusFilter === null : statusFilter === item;
              return (
                <TouchableOpacity
                  onPress={() => setStatusFilter(item === "ALL" ? null : isSelected ? null : item)}
                  style={[
                    styles.filterChip,
                    {
                      backgroundColor: isSelected ? "rgba(7, 159, 189, 0.18)" : colors.surface,
                      borderColor: isSelected ? colors.primary : colors.border,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.filterChipText,
                      { color: isSelected ? colors.primary : colors.textSecondary },
                    ]}
                  >
                    {item.replace(/_/g, " ")}
                  </Text>
                </TouchableOpacity>
              );
            }}
          />
        </View>

        <View style={styles.actionRow}>
          <Text style={[styles.resultsCount, { color: colors.textSecondary }]}>
            {filteredAndSorted.length} {filteredAndSorted.length === 1 ? "Exam" : "Exams"}
          </Text>
          <Button
            title="Create Exam"
            icon={<Ionicons name="add" size={16} color="#FFFFFF" />}
            variant="gradient"
            size="small"
            onPress={() => navigation.navigate("ExamCreate")}
          />
        </View>
      </View>

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
            icon="document-text-outline"
            title="No exams found"
            description={
              search || statusFilter
                ? "No examinations match your filter criteria."
                : "Create an examination to start processing question papers and answer sheets."
            }
            actionTitle={search || statusFilter ? undefined : "Create Exam"}
            onAction={() => navigation.navigate("ExamCreate")}
          />
        }
        renderItem={({ item }) => (
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={() => navigation.navigate("ExamWorkspace", { examId: item.id })}
          >
            <Card style={styles.card}>
              <View style={styles.cardHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.examName, { color: colors.text }]}>
                    {item.name}
                  </Text>
                  <Text style={[styles.examMeta, { color: colors.textSecondary }]}>
                    {item.class_name} • {item.subject_name} ({item.academic_year})
                  </Text>
                </View>
                <StatusBadge status={item.status} />
              </View>

              <View style={[styles.cardDetails, { borderColor: colors.border }]}>
                <View style={styles.detailCol}>
                  <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>Total Marks</Text>
                  <Text style={[styles.detailValue, { color: colors.text }]}>{item.total_marks}</Text>
                </View>
                <View style={styles.detailCol}>
                  <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>Exam Type</Text>
                  <Text style={[styles.detailValue, { color: colors.text }]}>{item.exam_type}</Text>
                </View>
                <View style={styles.detailCol}>
                  <Text style={[styles.detailLabel, { color: colors.textSecondary }]}>Next Action</Text>
                  <Text style={[styles.nextActionText, { color: colors.primary }]}>
                    {item.status === "DRAFT"
                      ? "Upload Paper"
                      : item.status === "QUESTION_PAPER_UPLOADED"
                      ? "Processing Paper"
                      : item.status === "QUESTIONS_EXTRACTED"
                      ? "Verify Questions"
                      : item.status === "QUESTIONS_VERIFIED"
                      ? "Add Answer Key"
                      : item.status === "ANSWER_KEY_UPLOADED"
                      ? "Verify Keys"
                      : item.status === "ANSWER_KEY_VERIFIED"
                      ? "Verify Exam"
                      : item.status === "READY_FOR_EVALUATION"
                      ? "Upload Sheets"
                      : item.status === "EVALUATING"
                      ? "Evaluating"
                      : item.status === "REVIEW_REQUIRED"
                      ? "Review Evals"
                      : "View Results"}
                  </Text>
                </View>
              </View>

              <View style={[styles.cardFooter, { borderTopColor: colors.border }]}>
                <TouchableOpacity
                  style={styles.deleteButton}
                  onPress={() => handleDeleteExam(item)}
                >
                  <Ionicons name="trash-outline" size={16} color={colors.error} />
                  <Text style={[styles.deleteText, { color: colors.error }]}>Delete</Text>
                </TouchableOpacity>

                <View style={styles.workspaceLink}>
                  <Text style={[styles.workspaceText, { color: colors.primary }]}>Open Workspace</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.primary} />
                </View>
              </View>
            </Card>
          </TouchableOpacity>
        )}
        ListFooterComponent={
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={setPage}
            totalItems={filteredAndSorted.length}
          />
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  topBar: {
    paddingHorizontal: 16,
    paddingTop: 12,
  },
  filterBar: {
    marginBottom: 8,
  },
  statusChips: {
    gap: 6,
    paddingBottom: 4,
  },
  filterChip: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  filterChipText: {
    fontSize: 11,
    fontWeight: "600",
  },
  actionRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  resultsCount: {
    fontSize: 12,
    fontWeight: "500",
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  card: {
    marginBottom: 12,
    padding: 16,
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  examName: {
    fontSize: 16,
    fontWeight: "700",
  },
  examMeta: {
    fontSize: 12,
    marginTop: 4,
  },
  cardDetails: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderBottomWidth: 1,
  },
  detailCol: {
    flex: 1,
  },
  detailLabel: {
    fontSize: 11,
    fontWeight: "500",
  },
  detailValue: {
    fontSize: 13,
    fontWeight: "700",
    marginTop: 2,
  },
  nextActionText: {
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },
  cardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 10,
    paddingTop: 8,
  },
  deleteButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 4,
  },
  deleteText: {
    fontSize: 12,
    fontWeight: "600",
  },
  workspaceLink: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  workspaceText: {
    fontSize: 13,
    fontWeight: "600",
  },
});
