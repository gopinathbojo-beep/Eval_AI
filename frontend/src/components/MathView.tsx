import { useMemo } from "react";
import katex from "katex";

interface MathViewProps {
  text?: string | null;
  className?: string;
  inline?: boolean;
}

interface MathToken {
  type: "text" | "inline-math" | "block-math";
  value: string;
}

/**
 * Normalizes math expressions before tokenization:
 * 1. Repairs unmatched closing delimiters (e.g. lines ending in \) without opening \()
 * 2. Detects bare equations (e.g. "1. A_{trapezium} = \frac{1}{2}(a+b)h") and wraps them in \( ... \)
 * 3. Keeps numbering and labels (e.g. "1. ", "(a) ") outside math delimiters.
 */
function normalizeMathText(raw: string): string {
  const lines = raw.split("\n");
  const processedLines = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return line;

    // Check for unmatched closing \) or \] at end of line without opening \( or \[
    if ((trimmed.endsWith("\\)") || trimmed.endsWith("\\]")) && !trimmed.includes("\\(") && !trimmed.includes("\\[")) {
      const stripped = trimmed.replace(/(?:\\[\)]|\\[\]])$/, "").trim();
      const labelMatch = stripped.match(/^([0-9]+\.|\([a-zA-Z0-9]+\)|[a-zA-Z]\.|\bQ[0-9]+[a-z]?\.?)\s+/);
      if (labelMatch) {
        const lbl = labelMatch[0];
        const rest = stripped.slice(lbl.length);
        return line.replace(trimmed, `${lbl}\\( ${rest} \\)`);
      } else {
        return line.replace(trimmed, `\\( ${stripped} \\)`);
      }
    }

    // Check for bare formula lines that have = and math indicators (\frac, _{...}, ^{...}, \times, \div, \sqrt, \,)
    // but no delimiters \( or \[ or $$
    const hasMathDelim = trimmed.includes("\\(") || trimmed.includes("\\[") || trimmed.includes("$$") || trimmed.includes("$");
    const hasMathIndicator = /\\frac|\\sqrt|_\{[a-zA-Z0-9_]+\}|\^\{?[0-9a-zA-Z+-]+\}?|\\times|\\div|\\pm|\\pi|\\cdot|\\,|×|÷/.test(trimmed);
    const hasEquation = trimmed.includes("=") || trimmed.includes("≈");

    if (!hasMathDelim && hasMathIndicator && hasEquation) {
      const labelMatch = trimmed.match(/^([0-9]+\.|\([a-zA-Z0-9]+\)|[a-zA-Z]\.|\bQ[0-9]+[a-z]?\.?)\s+/);
      if (labelMatch) {
        const lbl = labelMatch[0];
        const rest = trimmed.slice(lbl.length);
        return line.replace(trimmed, `${lbl}\\( ${rest} \\)`);
      } else {
        return line.replace(trimmed, `\\( ${trimmed} \\)`);
      }
    }

    return line;
  });

  return processedLines.join("\n");
}

/**
 * Pre-processes LaTeX math expressions before passing to KaTeX:
 * 1. Replaces unicode multiplication × with \times and ÷ with \div
 * 2. Converts multi-letter subscripts like _{trapezium} to _{\text{trapezium}}
 * 3. Wraps multi-word descriptive phrases (like "Cross-sectional Area") in \text{...}
 */
function sanitizeLatexForKaTeX(expr: string): string {
  let res = expr;
  // Replace unicode × and ÷
  res = res.replace(/×/g, " \\times ");
  res = res.replace(/÷/g, " \\div ");
  // Convert multi-letter subscripts like _{trapezium} or _{prism} to _{\text{trapezium}}
  res = res.replace(/_\{([a-zA-Z]{2,})\}/g, "_{\\text{$1}}");
  // Multi-word English phrases like "Cross-sectional Area"
  res = res.replace(/\b([A-Z][a-zA-Z]*(?:-[a-zA-Z]+)?(?:\s+[A-Za-z]+)+)\b/g, (m) => {
    return `\\text{${m}}`;
  });
  // Single capitalized words longer than 3 chars that are surrounded by math operators (e.g. "Length")
  res = res.replace(/(?<=(?:=|\+|-|\\times|\\div|\*|\/)\s*)([A-Z][a-z]{3,})\b/g, "\\text{$1}");
  return res;
}

/**
 * Splits text into plain text and LaTeX math blocks.
 * Supports:
 * - $$ ... $$ (block math)
 * - \[ ... \] or \\[ ... \\] (block math)
 * - \( ... \) or \\( ... \\) (inline math)
 * - $ ... $ (inline math)
 * - Bare LaTeX expressions containing \frac, \sqrt, \left( \right)
 */
function parseMathTokens(raw: string): MathToken[] {
  const normalized = normalizeMathText(raw);

  // Regex matching standard LaTeX math wrappers
  const mathWrapperRegex = /(\$\$[\s\S]+?\$\$|(?:\\[\[]|\\\\\[)[\s\S]+?(?:\\[\]]|\\\\\])|(?:\\[\(]|\\\\[\(])[\s\S]+?(?:\\[\)]|\\\\[\)])|\$(?!\s)[^$\n]+?(?<!\s)\$)/g;

  const tokens: MathToken[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = mathWrapperRegex.exec(normalized)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ type: "text", value: normalized.slice(lastIndex, match.index) });
    }

    const rawMatch = match[0];
    if (rawMatch.startsWith("$$") && rawMatch.endsWith("$$")) {
      tokens.push({ type: "block-math", value: rawMatch.slice(2, -2).trim() });
    } else if (rawMatch.startsWith("\\[") || rawMatch.startsWith("\\\\[")) {
      const stripped = rawMatch.replace(/^(?:\\[\[]|\\\\\[)/, "").replace(/(?:\\[\]]|\\\\\])$/, "");
      tokens.push({ type: "block-math", value: stripped.trim() });
    } else if (rawMatch.startsWith("\\(") || rawMatch.startsWith("\\\\(")) {
      const stripped = rawMatch.replace(/^(?:\\[\(]|\\\\[\(])/, "").replace(/(?:\\[\)]|\\\\[\)])$/, "");
      tokens.push({ type: "inline-math", value: stripped.trim() });
    } else if (rawMatch.startsWith("$") && rawMatch.endsWith("$")) {
      tokens.push({ type: "inline-math", value: rawMatch.slice(1, -1).trim() });
    }

    lastIndex = mathWrapperRegex.lastIndex;
  }

  if (lastIndex < normalized.length) {
    tokens.push({ type: "text", value: normalized.slice(lastIndex) });
  }

  // Secondary pass: Detect bare LaTeX commands inside text tokens (e.g. \frac{a}{b}, \left( ... \right))
  const finalTokens: MathToken[] = [];
  const bareLatexRegex = /((?:\\left\(|\\frac\{|\\sqrt\{)[^\n]+?(?:\\right\)|(?<=\}))(?:\^(?:\{[^{}]+\}|[0-9a-zA-Z+-]+))?)/g;

  for (const token of tokens) {
    if (token.type !== "text") {
      finalTokens.push(token);
      continue;
    }

    let tLast = 0;
    let bMatch: RegExpExecArray | null;
    while ((bMatch = bareLatexRegex.exec(token.value)) !== null) {
      if (bMatch.index > tLast) {
        finalTokens.push({ type: "text", value: token.value.slice(tLast, bMatch.index) });
      }
      finalTokens.push({ type: "inline-math", value: bMatch[0].trim() });
      tLast = bareLatexRegex.lastIndex;
    }

    if (tLast < token.value.length) {
      finalTokens.push({ type: "text", value: token.value.slice(tLast) });
    }
  }

  return finalTokens;
}

export function MathView({ text, className = "", inline = false }: MathViewProps) {
  const renderedElements = useMemo(() => {
    if (!text) return null;

    const tokens = parseMathTokens(text);

    return tokens.map((token, idx) => {
      if (token.type === "block-math") {
        try {
          const sanitized = sanitizeLatexForKaTeX(token.value);
          const html = katex.renderToString(sanitized, {
            displayMode: true,
            throwOnError: false,
          });
          return (
            <div
              key={idx}
              className="my-2 overflow-x-auto py-1 text-center"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        } catch {
          return (
            <pre key={idx} className="my-2 overflow-x-auto text-xs text-mark">
              {token.value}
            </pre>
          );
        }
      }

      if (token.type === "inline-math") {
        try {
          const sanitized = sanitizeLatexForKaTeX(token.value);
          const html = katex.renderToString(sanitized, {
            displayMode: false,
            throwOnError: false,
          });
          return (
            <span
              key={idx}
              className="inline-block px-0.5 align-middle"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          );
        } catch {
          return (
            <code key={idx} className="text-xs text-mark">
              {token.value}
            </code>
          );
        }
      }

      // Plain text: preserve line breaks
      return (
        <span key={idx} className="whitespace-pre-wrap">
          {token.value}
        </span>
      );
    });
  }, [text]);


  if (!text) return <span className="text-mute">&ndash;</span>;

  const Tag = inline ? "span" : "div";
  return (
    <Tag className={`math-view leading-relaxed ${className}`}>
      {renderedElements}
    </Tag>
  );
}
