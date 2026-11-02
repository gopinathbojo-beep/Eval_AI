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
import type { Subject } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { SearchBar } from "../../components/SearchBar";
import { Pagination } from "../../components/Pagination";
import { ModalDialog } from "../../components/ModalDialog";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { Badge } from "../../components/Badge";

interface SubjectsScreenProps {
  navigation: any;
}

const ITEMS_PER_PAGE = 8;

export const SubjectsScreen: React.FC<SubjectsScreenProps> = () => {
  const { colors } = useTheme();

  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<"name" | "code">("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

  // Modal State
  const [modalVisible, setModalVisible] = useState(false);
  const [editingSubject, setEditingSubject] = useState<Subject | null>(null);
  const [nameInput, setNameInput] = useState("");
  const [codeInput, setCodeInput] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchSubjects = useCallback(async () => {
    try {
      const res = await api<Subject[]>("/subjects");
      setSubjects(res);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load subjects");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchSubjects();
  }, [fetchSubjects]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchSubjects();
  };

  const handleOpenAdd = () => {
    setEditingSubject(null);
    setNameInput("");
    setCodeInput("");
    setModalVisible(true);
  };

  const handleOpenEdit = (s: Subject) => {
    setEditingSubject(s);
    setNameInput(s.name);
    setCodeInput(s.code || "");
    setModalVisible(true);
  };

  const handleSaveSubject = async () => {
    if (!nameInput.trim()) {
      Alert.alert("Validation", "Subject name cannot be empty.");
      return;
    }
    try {
      setSaving(true);
      if (editingSubject) {
        await api<Subject>(`/subjects/${editingSubject.id}`, {
          method: "PATCH",
          json: {
            name: nameInput.trim(),
            code: codeInput.trim() || null,
          },
        });
        Alert.alert("Success", "Subject updated successfully.");
      } else {
        await api<Subject>("/subjects", {
          method: "POST",
          json: {
            name: nameInput.trim(),
            code: codeInput.trim() || null,
          },
        });
      }
      setModalVisible(false);
      setNameInput("");
      setCodeInput("");
      setEditingSubject(null);
      fetchSubjects();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to save subject");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSubject = (s: Subject) => {
    Alert.alert(
      "Delete Subject",
      `Are you sure you want to delete subject "${s.name}"? This will also remove any exams associated with this subject.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              setSaving(true);
              await api(`/subjects/${s.id}`, { method: "DELETE" });
              setModalVisible(false);
              setEditingSubject(null);
              fetchSubjects();
            } catch (err: any) {
              Alert.alert("Error", err.message || "Failed to delete subject.");
            } finally {
              setSaving(false);
            }
          },
        },
      ]
    );
  };

  const toggleSort = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  const filteredAndSorted = useMemo(() => {
    let result = subjects.filter(
      (s) =>
        s.name.toLowerCase().includes(search.toLowerCase()) ||
        (s.code && s.code.toLowerCase().includes(search.toLowerCase()))
    );

    result.sort((a, b) => {
      if (sortKey === "name") {
        const comp = a.name.localeCompare(b.name);
        return sortOrder === "asc" ? comp : -comp;
      } else {
        const codeA = a.code || "";
        const codeB = b.code || "";
        const comp = codeA.localeCompare(codeB);
        return sortOrder === "asc" ? comp : -comp;
      }
    });

    return result;
  }, [subjects, search, sortKey, sortOrder]);

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
        <Loading message="Loading subjects..." />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.topBar}>
        <SearchBar
          value={search}
          onChangeText={setSearch}
          placeholder="Search subjects or codes..."
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
                    sortKey === "name" ? "rgba(15, 118, 110, 0.15)" : colors.surface,
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
              onPress={() => setSortKey("code")}
              style={[
                styles.chip,
                {
                  backgroundColor:
                    sortKey === "code" ? "rgba(15, 118, 110, 0.15)" : colors.surface,
                  borderColor: sortKey === "code" ? colors.primary : colors.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  { color: sortKey === "code" ? colors.primary : colors.textSecondary },
                ]}
              >
                Sort: Code
              </Text>
            </TouchableOpacity>
          </View>

          <Button
            title="Add Subject"
            icon={<Ionicons name="add" size={16} color="#FFFFFF" />}
            variant="gradient"
            size="small"
            onPress={handleOpenAdd}
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
            icon="book-outline"
            title="No subjects found"
            description={
              search ? "No subjects match your search query." : "Add courses and subjects to your curriculum."
            }
            actionTitle={search ? undefined : "Add Subject"}
            onAction={handleOpenAdd}
          />
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <View
                style={[
                  styles.iconCircle,
                  { backgroundColor: "rgba(23, 130, 87, 0.12)" },
                ]}
              >
                <Ionicons name="book" size={20} color={colors.brandGreen} />
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={[styles.subjectName, { color: colors.text }]}>
                  {item.name}
                </Text>
                <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                  Course Code: {item.code || "None specified"}
                </Text>
              </View>
              {item.code ? (
                <Badge label={item.code} variant="teal" />
              ) : (
                <Badge label="Standard" variant="muted" />
              )}
              <TouchableOpacity
                style={{ padding: 6, marginLeft: 6 }}
                onPress={() => handleOpenEdit(item)}
              >
                <Ionicons name="pencil-outline" size={17} color={colors.primary} />
              </TouchableOpacity>
              <TouchableOpacity
                style={{ padding: 6, marginLeft: 2 }}
                onPress={() => handleDeleteSubject(item)}
              >
                <Ionicons name="trash-outline" size={17} color={colors.error} />
              </TouchableOpacity>
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
        onClose={() => {
          setModalVisible(false);
          setEditingSubject(null);
        }}
        title={editingSubject ? `Edit Subject (${editingSubject.name})` : "Add New Subject"}
        subtitle={
          editingSubject
            ? "Update subject name or course code"
            : "Define a subject or course module"
        }
      >
        <Input
          label="Subject Name"
          placeholder="e.g. Mathematics, Science, Literature"
          value={nameInput}
          onChangeText={setNameInput}
          autoFocus
        />
        <Input
          label="Course Code (Optional)"
          placeholder="e.g. MATH-101, SCI-204"
          value={codeInput}
          onChangeText={setCodeInput}
          autoCapitalize="characters"
        />
        <Button
          title={editingSubject ? "Save Changes" : "Create Subject"}
          onPress={handleSaveSubject}
          variant="gradient"
          loading={saving}
          fullWidth
          style={{ marginTop: 12 }}
        />

        {editingSubject && (
          <Button
            title="Delete Subject"
            onPress={() => handleDeleteSubject(editingSubject)}
            variant="outline"
            fullWidth
            style={{ marginTop: 8, borderColor: colors.error }}
            textStyle={{ color: colors.error }}
          />
        )}
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
    alignItems: "center",
    justifyContent: "center",
  },
  subjectName: {
    fontSize: 16,
    fontWeight: "700",
  },
  metaText: {
    fontSize: 11,
    marginTop: 2,
  },
});
