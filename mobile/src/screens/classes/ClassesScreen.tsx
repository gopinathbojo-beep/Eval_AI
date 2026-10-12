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
import type { ClassRow } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { SearchBar } from "../../components/SearchBar";
import { Pagination } from "../../components/Pagination";
import { ModalDialog } from "../../components/ModalDialog";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { Badge } from "../../components/Badge";

interface ClassesScreenProps {
  navigation: any;
}

const ITEMS_PER_PAGE = 8;

export const ClassesScreen: React.FC<ClassesScreenProps> = ({ navigation }) => {
  const { colors } = useTheme();

  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<"name" | "count">("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

  // Modal State
  const [modalVisible, setModalVisible] = useState(false);
  const [classNameInput, setClassNameInput] = useState("");
  const [creating, setCreating] = useState(false);

  const fetchClasses = useCallback(async () => {
    try {
      const res = await api<ClassRow[]>("/classes");
      setClasses(res);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load classes");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchClasses();
  }, [fetchClasses]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchClasses();
  };

  const handleCreate = async () => {
    if (!classNameInput.trim()) {
      Alert.alert("Validation", "Class name cannot be empty.");
      return;
    }
    try {
      setCreating(true);
      await api<ClassRow>("/classes", {
        method: "POST",
        json: { name: classNameInput.trim() },
      });
      setModalVisible(false);
      setClassNameInput("");
      fetchClasses();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to create class");
    } finally {
      setCreating(false);
    }
  };

  const toggleSort = () => {
    if (sortOrder === "asc") {
      setSortOrder("desc");
    } else {
      setSortOrder("asc");
    }
  };

  const filteredAndSorted = useMemo(() => {
    let result = classes.filter((c) =>
      c.name.toLowerCase().includes(search.toLowerCase())
    );

    result.sort((a, b) => {
      if (sortKey === "name") {
        const comp = a.name.localeCompare(b.name);
        return sortOrder === "asc" ? comp : -comp;
      } else {
        const comp = a.student_count - b.student_count;
        return sortOrder === "asc" ? comp : -comp;
      }
    });

    return result;
  }, [classes, search, sortKey, sortOrder]);

  const totalPages = Math.ceil(filteredAndSorted.length / ITEMS_PER_PAGE) || 1;
  const paginatedData = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return filteredAndSorted.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredAndSorted, page]);

  useEffect(() => {
    setPage(1);
  }, [search, sortKey, sortOrder]);

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading classes..." />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.topBar}>
        <SearchBar
          value={search}
          onChangeText={setSearch}
          placeholder="Search classes..."
          onSortPress={toggleSort}
          sortDirection={sortOrder}
        />

        <View style={styles.filterRow}>
          <View style={styles.sortChips}>
            <TouchableOpacity
              onPress={() => setSortKey("name")}
              style={[
                styles.chip,
                {
                  backgroundColor:
                    sortKey === "name" ? "rgba(7, 159, 189, 0.15)" : colors.surface,
                  borderColor: sortKey === "name" ? colors.primary : colors.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  { color: sortKey === "name" ? colors.primary : colors.textSecondary },
                ]}
              >
                Sort: Name ({sortOrder.toUpperCase()})
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setSortKey("count")}
              style={[
                styles.chip,
                {
                  backgroundColor:
                    sortKey === "count" ? "rgba(7, 159, 189, 0.15)" : colors.surface,
                  borderColor: sortKey === "count" ? colors.primary : colors.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  { color: sortKey === "count" ? colors.primary : colors.textSecondary },
                ]}
              >
                Sort: Students
              </Text>
            </TouchableOpacity>
          </View>

          <Button
            title="Add Class"
            icon={<Ionicons name="add" size={16} color="#FFFFFF" />}
            variant="gradient"
            size="small"
            onPress={() => setModalVisible(true)}
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
            icon="school-outline"
            title="No classes found"
            description={
              search ? "No classes match your search query." : "Add your first classroom or grade."
            }
            actionTitle={search ? undefined : "Add Class"}
            onAction={() => setModalVisible(true)}
          />
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <View style={styles.iconCircle}>
                <Ionicons name="school" size={20} color={colors.primary} />
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={[styles.className, { color: colors.text }]}>
                  {item.name}
                </Text>
                <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                  Classroom ID: {item.id.slice(0, 8)}...
                </Text>
              </View>
              <Badge
                label={`${item.student_count} Students`}
                variant={item.student_count > 0 ? "teal" : "muted"}
              />
            </View>

            <View style={[styles.cardFooter, { borderTopColor: colors.border }]}>
              <TouchableOpacity
                style={styles.viewStudentsBtn}
                onPress={() => navigation.navigate("Students", { filterClassId: item.id })}
              >
                <Ionicons name="people-outline" size={16} color={colors.primary} />
                <Text style={[styles.viewStudentsText, { color: colors.primary }]}>
                  View Enrolled Students
                </Text>
              </TouchableOpacity>
              <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
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

      <ModalDialog
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Add New Class"
        subtitle="Create a class section or grade for examinations"
      >
        <Input
          label="Class Name"
          placeholder="e.g. Grade 10-A, Class 12-B"
          value={classNameInput}
          onChangeText={setClassNameInput}
          autoFocus
        />
        <Button
          title="Create Class"
          onPress={handleCreate}
          variant="gradient"
          loading={creating}
          fullWidth
        />
      </ModalDialog>
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
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  sortChips: {
    flexDirection: "row",
    gap: 6,
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
    marginBottom: 10,
    padding: 14,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  iconCircle: {
    width: 42,
    height: 42,
    borderRadius: 10,
    backgroundColor: "rgba(7, 159, 189, 0.12)",
    alignItems: "center",
    justifyContent: "center",
  },
  className: {
    fontSize: 16,
    fontWeight: "700",
  },
  metaText: {
    fontSize: 11,
    marginTop: 2,
  },
  cardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 12,
    paddingTop: 10,
    borderTopWidth: 1,
  },
  viewStudentsBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  viewStudentsText: {
    fontSize: 12,
    fontWeight: "600",
  },
});
