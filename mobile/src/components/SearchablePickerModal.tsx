import React, { useState, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../theme/ThemeContext";
import { ModalDialog } from "./ModalDialog";
import { Input } from "./Input";
import { Button } from "./Button";

export interface PickerItem {
  id: string;
  label: string;
  subLabel?: string;
}

export interface CreateConfig {
  buttonLabel: string;
  inputLabel: string;
  inputPlaceholder: string;
  extraInputLabel?: string;
  extraInputPlaceholder?: string;
  onCreate: (value: string, extraValue?: string) => Promise<void>;
}

interface SearchablePickerModalProps {
  visible: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  searchPlaceholder?: string;
  items: PickerItem[];
  selectedId: string;
  onSelect: (item: PickerItem) => void;
  createConfig?: CreateConfig;
}

export const SearchablePickerModal: React.FC<SearchablePickerModalProps> = ({
  visible,
  onClose,
  title,
  subtitle,
  searchPlaceholder = "Search options...",
  items,
  selectedId,
  onSelect,
  createConfig,
}) => {
  const { colors } = useTheme();

  const [search, setSearch] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newExtra, setNewExtra] = useState("");
  const [creating, setCreating] = useState(false);

  React.useEffect(() => {
    if (visible) {
      setSearch("");
      setShowCreateForm(false);
      setNewLabel("");
      setNewExtra("");
    }
  }, [visible]);

  const filteredItems = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase().trim();
    return items.filter(
      (it) =>
        it.label.toLowerCase().includes(q) ||
        (it.subLabel && it.subLabel.toLowerCase().includes(q))
    );
  }, [items, search]);

  const handleCreateSubmit = async () => {
    if (!newLabel.trim()) {
      Alert.alert("Validation", "Please enter a name.");
      return;
    }
    if (!createConfig) return;

    try {
      setCreating(true);
      await createConfig.onCreate(newLabel.trim(), newExtra.trim() || undefined);
      setShowCreateForm(false);
      setNewLabel("");
      setNewExtra("");
    } catch (err: any) {
      Alert.alert("Creation Error", err.message || "Failed to create new item.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <ModalDialog visible={visible} onClose={onClose} title={title} subtitle={subtitle}>
      {/* Search Input */}
      <Input
        placeholder={searchPlaceholder}
        value={search}
        onChangeText={setSearch}
        leftIcon={<Ionicons name="search-outline" size={18} color={colors.textSecondary} />}
        clearButtonMode="while-editing"
      />

      {/* Optional Create New Form Toggle or Inline Creator */}
      {createConfig && (
        <View style={{ marginBottom: 10 }}>
          {!showCreateForm ? (
            <TouchableOpacity
              onPress={() => setShowCreateForm(true)}
              style={[
                styles.addNewButton,
                { backgroundColor: "rgba(7, 159, 189, 0.08)", borderColor: colors.primary },
              ]}
            >
              <Ionicons name="add-circle-outline" size={18} color={colors.primary} />
              <Text style={[styles.addNewButtonText, { color: colors.primary }]}>
                {createConfig.buttonLabel}
              </Text>
            </TouchableOpacity>
          ) : (
            <View
              style={[
                styles.createFormBox,
                { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
              ]}
            >
              <View style={styles.createFormHeader}>
                <Text style={[styles.createFormTitle, { color: colors.text }]}>
                  {createConfig.buttonLabel}
                </Text>
                <TouchableOpacity onPress={() => setShowCreateForm(false)}>
                  <Ionicons name="close" size={18} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>

              <Input
                label={createConfig.inputLabel}
                placeholder={createConfig.inputPlaceholder}
                value={newLabel}
                onChangeText={setNewLabel}
                autoFocus
              />

              {createConfig.extraInputLabel && (
                <Input
                  label={createConfig.extraInputLabel}
                  placeholder={createConfig.extraInputPlaceholder}
                  value={newExtra}
                  onChangeText={setNewExtra}
                />
              )}

              <View style={{ flexDirection: "row", gap: 8, marginTop: 4 }}>
                <Button
                  title="Cancel"
                  variant="secondary"
                  size="small"
                  onPress={() => setShowCreateForm(false)}
                  style={{ flex: 1 }}
                />
                <Button
                  title="Save & Select"
                  icon={<Ionicons name="checkmark" size={16} color="#FFFFFF" />}
                  variant="gradient"
                  size="small"
                  loading={creating}
                  onPress={handleCreateSubmit}
                  style={{ flex: 1 }}
                />
              </View>
            </View>
          )}
        </View>
      )}

      {/* Items List */}
      <ScrollView
        style={[styles.itemsList, { borderColor: colors.border }]}
        keyboardShouldPersistTaps="handled"
      >
        {filteredItems.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Ionicons name="search" size={24} color={colors.textSecondary} />
            <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
              No options match "{search}"
            </Text>
            {createConfig && !showCreateForm && (
              <Button
                title={`Create "${search}"`}
                size="small"
                variant="outline"
                onPress={() => {
                  setNewLabel(search);
                  setShowCreateForm(true);
                }}
                style={{ marginTop: 8 }}
              />
            )}
          </View>
        ) : (
          filteredItems.map((item) => {
            const isSelected = selectedId === item.id;
            return (
              <TouchableOpacity
                key={item.id}
                onPress={() => {
                  onSelect(item);
                  onClose();
                }}
                style={[
                  styles.itemRow,
                  { borderBottomColor: colors.border },
                  isSelected && {
                    backgroundColor: "rgba(7, 159, 189, 0.12)",
                    borderColor: colors.primary,
                  },
                ]}
              >
                <View style={{ flex: 1, marginRight: 8 }}>
                  <Text
                    style={[
                      styles.itemLabel,
                      { color: isSelected ? colors.primary : colors.text },
                      isSelected && { fontWeight: "700" },
                    ]}
                  >
                    {item.label}
                  </Text>
                  {item.subLabel ? (
                    <Text style={[styles.itemSubLabel, { color: colors.textSecondary }]}>
                      {item.subLabel}
                    </Text>
                  ) : null}
                </View>

                {isSelected ? (
                  <Ionicons name="checkmark-circle" size={20} color={colors.primary} />
                ) : (
                  <Ionicons name="chevron-forward" size={16} color={colors.textSecondary} />
                )}
              </TouchableOpacity>
            );
          })
        )}
      </ScrollView>

      <Button
        title="Close"
        variant="secondary"
        onPress={onClose}
        style={{ marginTop: 12 }}
        fullWidth
      />
    </ModalDialog>
  );
};

const styles = StyleSheet.create({
  addNewButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderStyle: "dashed",
  },
  addNewButtonText: {
    fontSize: 13,
    fontWeight: "700",
  },
  createFormBox: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
  },
  createFormHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  createFormTitle: {
    fontSize: 13,
    fontWeight: "700",
  },
  itemsList: {
    maxHeight: 260,
    borderRadius: 8,
    borderWidth: 1,
  },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  itemLabel: {
    fontSize: 14,
    fontWeight: "600",
  },
  itemSubLabel: {
    fontSize: 12,
    marginTop: 2,
  },
  emptyContainer: {
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  emptyText: {
    fontSize: 13,
    marginTop: 6,
    textAlign: "center",
  },
});
