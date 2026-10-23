import React, { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useTheme } from "../../theme/ThemeContext";
import { api, downloadAndShareFile } from "../../api/client";
import type { ResultResponse, ResultRow } from "../../types";
import { Card } from "../../components/Card";
import { Button } from "../../components/Button";
import { Badge, StatusBadge } from "../../components/Badge";
import { PenScore } from "../../components/PenScore";
import { Loading } from "../../components/Loading";
import { Empty } from "../../components/Empty";
import { OutcomeTables } from "../../components/OutcomeTables";
import { fonts } from "../../theme/colors";

interface ResultDetailScreenProps {
  route: any;
  navigation: any;
}

export const ResultDetailScreen: React.FC<ResultDetailScreenProps> = ({ route }) => {
  const { colors } = useTheme();
  const evaluationId = route.params.evaluationId;

  const [data, setData] = useState<ResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const fetchResult = useCallback(async () => {
    try {
      const res = await api<ResultResponse>(`/evaluations/${evaluationId}/result`);
      setData(res);
    } catch (err: any) {
      Alert.alert("Error", err.message || "Failed to load result breakdown");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [evaluationId]);

  useEffect(() => {
    fetchResult();
  }, [fetchResult]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchResult();
  };

  const handleDownloadPDF = async () => {
    try {
      setDownloading(true);
      const studentName = data?.evaluation.student?.name || "Student";
      const filename = `${studentName.replace(/\s+/g, "_")}_Examination_Report.pdf`;
      await downloadAndShareFile(`/evaluations/${evaluationId}/report.pdf`, filename);
    } catch (err: any) {
      Alert.alert("Download Error", err.message || "Failed to download PDF report");
    } finally {
      setDownloading(false);
    }
  };

  if (loading && !refreshing) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Loading message="Loading student examination marksheet..." />
      </View>
    );
  }

  if (!data) {
    return (
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <Empty title="Result Not Found" description="The requested marksheet could not be loaded." />
      </View>
    );
  }

  const { evaluation, exam, questions, total_marks, maximum_marks, percentage, finalized } = data;

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
            colors={[colors.primary]}
          />
        }
      >
        {/* Student & Overall Grade Card */}
        <Card style={styles.summaryCard}>
          <View style={styles.studentHeader}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.studentName, { color: colors.text }]}>
                {evaluation.student?.name}
              </Text>
              <Text style={[styles.studentMeta, { color: colors.textSecondary }]}>
                Roll No: {evaluation.student?.roll_number}
              </Text>
              <Text style={[styles.examInfo, { color: colors.textSecondary }]}>
                {exam.name} • {exam.class} • {exam.subject}
              </Text>
            </View>
            <StatusBadge status={finalized ? "FINALIZED" : evaluation.status} />
          </View>

          <View style={[styles.scoreRow, { borderColor: colors.border }]}>
            <View style={styles.scoreCol}>
              <Text style={[styles.scoreLabel, { color: colors.textSecondary }]}>Marks Secured</Text>
              <PenScore
                score={total_marks}
                maxScore={maximum_marks}
                size="large"
              />
            </View>

            <View style={styles.scoreCol}>
              <Text style={[styles.scoreLabel, { color: colors.textSecondary }]}>Percentage</Text>
              <Text style={[styles.percentageText, { color: colors.brandGreen }]}>
                {percentage.toFixed(1)}%
              </Text>
            </View>
          </View>

          <Button
            title="Download PDF Report"
            icon={<Ionicons name="document-text-outline" size={18} color="#FFFFFF" />}
            variant="gradient"
            loading={downloading}
            onPress={handleDownloadPDF}
            style={{ marginTop: 14 }}
          />
        </Card>

        {data.outcomes && <OutcomeTables outcomes={data.outcomes} />}

        {/* Section Heading */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          Question-Wise Performance Breakdown ({questions.length})
        </Text>

        {questions.map((row: ResultRow) => (
          <Card key={row.question_id} style={styles.rowCard}>
            <View style={styles.rowHeader}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Badge label={`Q${row.question}`} variant="teal" />
                {row.k_level && <Badge label={row.k_level} variant="muted" size="small" />}
                {row.course_outcome && <Badge label={row.course_outcome} variant="muted" size="small" />}
                {row.teacher_overridden && (
                  <Badge label="Teacher Overridden" variant="warning" />
                )}
              </View>
              <PenScore
                score={row.final_marks}
                maxScore={row.max_marks}
                overridden={row.teacher_overridden}
              />
            </View>

            <Text style={[styles.questionText, { color: colors.text }]}>
              {row.question_text || `Question ${row.question}`}
            </Text>

            {row.student_answer && (
              <View style={[styles.answerBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.boxLabel, { color: colors.brandGreen }]}>Student's Answer:</Text>
                <Text style={[styles.boxText, { color: colors.text }]}>{row.student_answer}</Text>
              </View>
            )}

            {row.official_answer && (
              <View style={[styles.answerBox, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
                <Text style={[styles.boxLabel, { color: colors.primary }]}>Official Solution:</Text>
                <Text style={[styles.boxText, { color: colors.text }]}>{row.official_answer}</Text>
              </View>
            )}

            {row.feedback && (
              <View style={[styles.feedbackBox, { borderColor: colors.border }]}>
                <Text style={[styles.feedbackLabel, { color: colors.textSecondary }]}>Feedback:</Text>
                <Text style={[styles.feedbackText, { color: colors.text }]}>{row.feedback}</Text>
              </View>
            )}
          </Card>
        ))}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  summaryCard: {
    padding: 18,
    marginBottom: 16,
  },
  studentHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  studentName: {
    fontSize: 20,
    fontWeight: "800",
  },
  studentMeta: {
    fontSize: 13,
    marginTop: 2,
    fontWeight: "600",
  },
  examInfo: {
    fontSize: 12,
    marginTop: 2,
  },
  scoreRow: {
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "center",
    marginTop: 16,
    paddingVertical: 14,
    borderTopWidth: 1,
    borderBottomWidth: 1,
  },
  scoreCol: {
    alignItems: "center",
  },
  scoreLabel: {
    fontSize: 12,
    fontWeight: "600",
    marginBottom: 6,
    textTransform: "uppercase",
  },
  percentageText: {
    fontSize: 28,
    fontWeight: "800",
  },
  sectionTitle: {
    fontSize: 17,
    fontFamily: fonts.display,
    fontWeight: "700",
    marginBottom: 12,
  },
  rowCard: {
    padding: 16,
    marginBottom: 12,
  },
  rowHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  questionText: {
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 20,
    marginBottom: 10,
  },
  answerBox: {
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 8,
  },
  boxLabel: {
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 2,
  },
  boxText: {
    fontSize: 12,
    lineHeight: 16,
  },
  feedbackBox: {
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    marginTop: 4,
  },
  feedbackLabel: {
    fontSize: 11,
    fontWeight: "600",
    marginBottom: 2,
  },
  feedbackText: {
    fontSize: 12,
    lineHeight: 16,
  },
});
