import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
  Alert,
  ScrollView,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api } from "../../api/client";
import type { Student, ClassRow } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { SearchBar } from "../../components/SearchBar";
import { Pagination } from "../../components/Pagination";
import { ModalDialog } from "../../components/ModalDialog";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { Badge } from "../../components/Badge";

interface StudentsScreenProps {
  route: any;
  navigation: any;
}

const ITEMS_PER_PAGE = 8;

export const StudentsScreen: React.FC<StudentsScreenProps> = ({ route }) => {
  const { colors } = useTheme();
  const initialClassId = route?.params?.filterClassId || null;

  const [students, setStudents] = useState<Student[]>([]);
  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string | null>(initialClassId);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<"name" | "roll">("roll");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

  // Modal State
  const [modalVisible, setModalVisible] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [rollInput, setRollInput] = useState("");
  const [modalClassId, setModalClassId] = useState<string>("");
  const [creating, setCreating] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [studentsRes, classesRes] = await Promise.all([
        api<Student[]>("/students"),
        api<ClassRow[]>("/classes"),
      ]);
      setStudents(studentsRes);
      setClasses(classesRes);
      if (classesRes.length > 0 && !modalClassId) {
        setModalClassId(classesRes[0].id);
      }
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load students data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [modalClassId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const handleCreate = async () => {
    if (!nameInput.trim() || !rollInput.trim() || !modalClassId) {
      Alert.alert("Validation", "Please fill in all fields and select a class.");
      return;
    }
    try {
      setCreating(true);
      await api<Student>("/students", {
        method: "POST",
        json: {
          name: nameInput.trim(),
          roll_number: rollInput.trim(),
          class_id: modalClassId,
        },
      });
      setModalVisible(false);
      setNameInput("");
      setRollInput("");
      fetchData();
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to add student");
    } finally {
      setCreating(false);
    }
  };

  const toggleSort = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
  };

  const filteredAndSorted = useMemo(() => {
    let result = students.filter((s) => {
      const matchSearch =
        s.name.toLowerCase().includes(search.toLowerCase()) ||
        s.roll_number.toLowerCase().includes(search.toLowerCase());
      const matchClass = selectedClassId ? s.class_id === selectedClassId : true;
      return matchSearch && matchClass;
    });

    result.sort((a, b) => {
      if (sortKey === "name") {
        const comp = a.name.localeCompare(b.name);
        return sortOrder === "asc" ? comp : -comp;
      } else {
        const comp = a.roll_number.localeCompare(b.roll_number, undefined, { numeric: true });
        return sortOrder === "asc" ? comp : -comp;
      }
    });

    return result;
  }, [students, search, selectedClassId, sortKey, sortOrder]);

  const totalPages = Math.ceil(filteredAndSorted.length / ITEMS_PER_PAGE) || 1;
  const paginatedData = useMemo(() => {
    const start = (page - 1) * ITEMS_PER_PAGE;
    return filteredAndSorted.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredAndSorted, page]);

  useEffect(() => {
    setPage(1);
  }, [search, selectedClassId, sortKey, sortOrder]);

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading student roster..." />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={styles.topBar}>
        <SearchBar
          value={search}
          onChangeText={setSearch}
          placeholder="Search by name or roll number..."
          onSortPress={toggleSort}
          sortDirection={sortOrder}
        />

        {/* Class Filter Chips */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.classChipsScroll}
        >
          <TouchableOpacity
            onPress={() => setSelectedClassId(null)}
            style={[
              styles.classChip,
              {
                backgroundColor:
                  selectedClassId === null ? "rgba(7, 159, 189, 0.18)" : colors.surface,
                borderColor: selectedClassId === null ? colors.primary : colors.border,
              },
            ]}
          >
            <Text
              style={[
                styles.classChipText,
                { color: selectedClassId === null ? colors.primary : colors.textSecondary },
              ]}
            >
              All Classes ({students.length})
            </Text>
          </TouchableOpacity>

          {classes.map((c) => {
            const isSelected = selectedClassId === c.id;
            return (
              <TouchableOpacity
                key={c.id}
                onPress={() => setSelectedClassId(isSelected ? null : c.id)}
                style={[
                  styles.classChip,
                  {
                    backgroundColor: isSelected ? "rgba(7, 159, 189, 0.18)" : colors.surface,
                    borderColor: isSelected ? colors.primary : colors.border,
                  },
                ]}
              >
                <Text
                  style={[
                    styles.classChipText,
                    { color: isSelected ? colors.primary : colors.textSecondary },
                  ]}
                >
                  {c.name}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <View style={styles.actionRow}>
          <View style={styles.sortChips}>
            <TouchableOpacity
              onPress={() => setSortKey("roll")}
              style={[
                styles.chip,
                {
                  backgroundColor:
                    sortKey === "roll" ? "rgba(7, 159, 189, 0.15)" : colors.surface,
                  borderColor: sortKey === "roll" ? colors.primary : colors.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  { color: sortKey === "roll" ? colors.primary : colors.textSecondary },
                ]}
              >
                Sort: Roll ({sortOrder.toUpperCase()})
              </Text>
            </TouchableOpacity>

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
                Sort: Name
              </Text>
            </TouchableOpacity>
          </View>

          <Button
            title="Add Student"
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
            icon="people-outline"
            title="No students found"
            description={
              search || selectedClassId
                ? "No students match your search or filter."
                : "Enroll students to start assigning examinations."
            }
            actionTitle={search || selectedClassId ? undefined : "Add Student"}
            onAction={() => setModalVisible(true)}
          />
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <View
                style={[
                  styles.avatarCircle,
                  { backgroundColor: "rgba(7, 159, 189, 0.12)" },
                ]}
              >
                <Text style={[styles.avatarText, { color: colors.primary }]}>
                  {item.name.charAt(0).toUpperCase()}
                </Text>
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={[styles.studentName, { color: colors.text }]}>
                  {item.name}
                </Text>
                <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                  Roll No: <Text style={{ color: colors.text, fontWeight: "600" }}>{item.roll_number}</Text>
                </Text>
              </View>
              <Badge
                label={item.class_name || "Unassigned"}
                variant={item.class_name ? "teal" : "muted"}
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

      <ModalDialog
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title="Add New Student"
        subtitle="Enroll student with their name and roll number"
      >
        <Input
          label="Full Name"
          placeholder="e.g. John Doe"
          value={nameInput}
          onChangeText={setNameInput}
          autoFocus
        />
        <Input
          label="Roll Number"
          placeholder="e.g. 101, A-12"
          value={rollInput}
          onChangeText={setRollInput}
        />

        <Text style={[styles.modalLabel, { color: colors.textSecondary }]}>
          Assign to Class
        </Text>
        <View style={styles.modalClassesGrid}>
          {classes.map((c) => {
            const isSelected = modalClassId === c.id;
            return (
              <TouchableOpacity
                key={c.id}
                onPress={() => setModalClassId(c.id)}
                style={[
                  styles.modalClassChip,
                  {
                    backgroundColor: isSelected ? "rgba(7, 159, 189, 0.18)" : colors.surface,
                    borderColor: isSelected ? colors.primary : colors.border,
                  },
                ]}
              >
                <Text
                  style={[
                    styles.modalClassText,
                    { color: isSelected ? colors.primary : colors.text },
                  ]}
                >
                  {c.name}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <Button
          title="Enroll Student"
          onPress={handleCreate}
          variant="gradient"
          loading={creating}
          fullWidth
          style={{ marginTop: 16 }}
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
  classChipsScroll: {
    flexDirection: "row",
    gap: 6,
    paddingBottom: 10,
  },
  classChip: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  classChipText: {
    fontSize: 12,
    fontWeight: "600",
  },
  actionRow: {
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
  avatarCircle: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: {
    fontSize: 18,
    fontWeight: "700",
  },
  studentName: {
    fontSize: 16,
    fontWeight: "700",
  },
  metaText: {
    fontSize: 12,
    marginTop: 2,
  },
  modalLabel: {
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  modalClassesGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  modalClassChip: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  modalClassText: {
    fontSize: 13,
    fontWeight: "600",
  },
});
