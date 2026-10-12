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
import { api, downloadAndShareFile } from "../../api/client";
import type { Evaluation } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { SearchBar } from "../../components/SearchBar";
import { Pagination } from "../../components/Pagination";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { StatusBadge } from "../../components/Badge";
import { PenScore } from "../../components/PenScore";

interface ResultsListScreenProps {
  navigation: any;
}

const ITEMS_PER_PAGE = 8;

export const ResultsListScreen: React.FC<ResultsListScreenProps> = ({ navigation }) => {
  const { colors } = useTheme();

  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Filters & Sorting
  const [search, setSearch] = useState("");
  const [filterFinalizedOnly, setFilterFinalizedOnly] = useState(false);
  const [sortKey, setSortKey] = useState<"percentage" | "name">("percentage");
  const [sortOrder, setSortOrder] = useState<"desc" | "asc">("desc");
  const [page, setPage] = useState(1);

  const fetchData = useCallback(async () => {
    try {
      const res = await api<Evaluation[]>("/evaluations");
      setEvaluations(res);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load results");
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

  const handleDownloadReport = async (item: Evaluation) => {
    try {
      setDownloadingId(item.id);
      const studentName = item.student?.name || "Student";
      const filename = `${studentName.replace(/\s+/g, "_")}_Report.pdf`;
      await downloadAndShareFile(`/evaluations/${item.id}/report.pdf`, filename);
    } catch (err: any) {
      Alert.alert("Download Error", err.message || "Failed to download PDF report");
    } finally {
      setDownloadingId(null);
    }
  };

  const toggleSort = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  const filteredAndSorted = useMemo(() => {
    let result = evaluations.filter((ev) => {
      const sName = ev.student?.name?.toLowerCase() || "";
      const sRoll = ev.student?.roll_number?.toLowerCase() || "";
      const eName = ev.exam_name?.toLowerCase() || "";
      const q = search.toLowerCase();
      const matchSearch = sName.includes(q) || sRoll.includes(q) || eName.includes(q);
      const matchFinalized = filterFinalizedOnly ? ev.status === "FINALIZED" : true;
      return matchSearch && matchFinalized;
    });

    result.sort((a, b) => {
      if (sortKey === "percentage") {
        const pA = a.percentage ?? -1;
        const pB = b.percentage ?? -1;
        return sortOrder === "desc" ? pB - pA : pA - pB;
      } else {
        const nameA = a.student?.name || "";
        const nameB = b.student?.name || "";
        const comp = nameA.localeCompare(nameB);
        return sortOrder === "asc" ? comp : -comp;
      }
    });

    return result;
  }, [evaluations, search, filterFinalizedOnly, sortKey, sortOrder]);

  const totalPages = Math.ceil(filteredAndSorted.length / ITEMS_PER_PAGE) || 1;
  const paginatedData = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return filteredAndSorted.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredAndSorted, page]);

  useEffect(() => {
    setPage(1);
  }, [search, filterFinalizedOnly, sortKey, sortOrder]);

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading evaluation results..." />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.topBar}>
        <SearchBar
          value={search}
          onChangeText={setSearch}
          placeholder="Search student, roll, or exam..."
          onSortPress={toggleSort}
          sortDirection={sortOrder}
        />

        <View style={styles.filterRow}>
          <View style={styles.chipsRow}>
            <TouchableOpacity
              onPress={() => setFilterFinalizedOnly(!filterFinalizedOnly)}
              style={[
                styles.chip,
                {
                  backgroundColor: filterFinalizedOnly
                    ? "rgba(81, 188, 117, 0.18)"
                    : colors.surface,
                  borderColor: filterFinalizedOnly ? colors.brandGreen : colors.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  { color: filterFinalizedOnly ? colors.brandGreen : colors.textSecondary },
                ]}
              >
                {filterFinalizedOnly ? "✓ Finalized Only" : "All Results"}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setSortKey(sortKey === "percentage" ? "name" : "percentage")}
              style={[
                styles.chip,
                {
                  backgroundColor: "rgba(7, 159, 189, 0.15)",
                  borderColor: colors.primary,
                },
              ]}
            >
              <Text style={[styles.chipText, { color: colors.primary }]}>
                Sort: {sortKey === "percentage" ? "% Score" : "Name"} ({sortOrder.toUpperCase()})
              </Text>
            </TouchableOpacity>
          </View>
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
            icon="ribbon-outline"
            title="No Results Found"
            description={
              search || filterFinalizedOnly
                ? "No evaluation results match your search or filters."
                : "Evaluated examination marksheets will appear here."
            }
          />
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <View style={{ flex: 1, marginRight: 8 }}>
                <Text style={[styles.studentName, { color: colors.text }]}>
                  {item.student?.name}
                </Text>
                <Text style={[styles.studentMeta, { color: colors.textSecondary }]}>
                  Roll: {item.student?.roll_number} • {item.exam_name || "Exam"}
                </Text>
              </View>
              <PenScore
                score={item.total_marks}
                maxScore={item.maximum_marks}
              />
            </View>

            <View style={[styles.cardMidRow, { borderTopColor: colors.border, borderBottomColor: colors.border }]}>
              <StatusBadge status={item.status} />
              {item.percentage !== null && item.percentage !== undefined && (
                <Text style={[styles.percentageText, { color: colors.brandGreen }]}>
                  {item.percentage.toFixed(1)}%
                </Text>
              )}
            </View>

            <View style={styles.btnRow}>
              <Button
                title="Download Report"
                icon={<Ionicons name="download-outline" size={14} color="#FFFFFF" />}
                variant="gradient"
                size="small"
                onPress={() => handleDownloadReport(item)}
                loading={downloadingId === item.id}
                style={{ flex: 1 }}
              />
              <Button
                title="View Result"
                icon={<Ionicons name="eye-outline" size={14} color={colors.text} />}
                variant="secondary"
                size="small"
                onPress={() => navigation.navigate("ResultDetail", { evaluationId: item.id })}
                style={{ flex: 1 }}
              />
            </View>
          </Card>
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
  filterRow: {
    marginBottom: 10,
  },
  chipsRow: {
    flexDirection: "row",
    gap: 8,
  },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  chipText: {
    fontSize: 11,
    fontWeight: "600",
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  card: {
    marginBottom: 12,
    padding: 14,
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  studentName: {
    fontSize: 16,
    fontWeight: "700",
  },
  studentMeta: {
    fontSize: 12,
    marginTop: 2,
  },
  cardMidRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 10,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderBottomWidth: 1,
  },
  percentageText: {
    fontSize: 16,
    fontWeight: "800",
  },
  btnRow: {
    flexDirection: "row",
    gap: 8,
    marginTop: 10,
  },
});
