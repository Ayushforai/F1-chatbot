const DISCOURSE_SPLIT =
  /(?<=[.!?])\s+(?=(?:Additionally|Furthermore|Moreover|However|In addition|In summary|Note that|The Power Unit|The cost cap|The budget cap|Article\s))/;

const MARKDOWN_BOLD = /\*\*([\s\S]+?)\*\*/g;

const AUTO_HIGHLIGHT =
  /\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand|millions|mn)\b)?\s*\(\s*₹[^)]+\)|\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand|millions|mn)\b)?(?:\s*\/\s*(?:₹|£|INR|GBP)[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand|crore|lakh)\b)?)*|£[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand)\b)?|₹[\d,]+(?:\.\d+)?(?:\s*(?:million|crore|lakh|billion)\b)?|\b(?:USD|INR|GBP)\s*[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand)\b)?|Article\s+[A-E]?\d+(?:\.\d+)*[a-z]?(?:\.[a-z])?|\b\d{1,2}:\d{2}(?::\d{2})?\.\d{3}\b/gi;

const LIST_LINE = /^(?:[-*•]|\d+[.)])\s+/;
const HEADING_LINE = /^(#{1,3})\s+(.+)$/;
const LABEL_HEADING = /^(Classified finishers.*|Did not finish.*|[A-Z][A-Za-z0-9 &'/-]{2,48}:)$/;

export function splitDenseParagraph(text) {
  const trimmed = text.trim();
  if (!trimmed || trimmed.includes("\n")) return trimmed ? [trimmed] : [];

  const discourse = trimmed.split(DISCOURSE_SPLIT).map((p) => p.trim()).filter(Boolean);
  if (discourse.length > 1) return discourse;

  if (trimmed.length < 220) return [trimmed];

  const sentences = trimmed.match(/[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$/g);
  if (!sentences || sentences.length < 3) return [trimmed];

  const grouped = [];
  for (let i = 0; i < sentences.length; i += 2) {
    grouped.push(sentences.slice(i, i + 2).join("").trim());
  }
  return grouped;
}

function splitBlocks(text) {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const raw = normalized.split(/\n{2,}/);
  const expanded = [];
  for (const chunk of raw) {
    const trimmed = chunk.trim();
    if (!trimmed) continue;
    const lines = trimmed.split("\n");
    const hasList = lines.some((line) => LIST_LINE.test(line.trim()));
    if (hasList || lines.length > 1) {
      expanded.push(trimmed);
    } else {
      expanded.push(...splitDenseParagraph(trimmed));
    }
  }
  return expanded;
}

function headingFromLine(line) {
  const md = line.match(HEADING_LINE);
  if (md) return { type: "heading", level: md[1].length, text: md[2].trim() };
  if (LABEL_HEADING.test(line)) {
    return { type: "heading", level: 3, text: line.replace(/:$/, "") };
  }
  return null;
}

function parseMixedBlock(block) {
  const lines = block.split("\n");
  const nodes = [];
  let list = null;
  let paragraphLines = [];

  const flushParagraph = () => {
    const text = paragraphLines.join(" ").trim();
    paragraphLines = [];
    if (!text) return;
    const heading = headingFromLine(text);
    if (heading) nodes.push(heading);
    else nodes.push({ type: "paragraph", text });
  };

  const flushList = () => {
    if (list) {
      nodes.push(list);
      list = null;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = headingFromLine(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      nodes.push(heading);
      continue;
    }

    if (LIST_LINE.test(trimmed)) {
      flushParagraph();
      const ordered = /^\d+[.)]\s+/.test(trimmed);
      const indent = Math.min(2, Math.floor((line.match(/^\s*/) || [""])[0].length / 2));
      const item = trimmed.replace(LIST_LINE, "");
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { type: "list", ordered, items: [] };
      }
      list.items.push({ text: item, indent });
      continue;
    }

    flushList();
    paragraphLines.push(trimmed);
  }

  flushParagraph();
  flushList();
  return nodes;
}

export function parseAnswer(text) {
  if (!text) return [];
  const nodes = [];
  for (const block of splitBlocks(text)) {
    nodes.push(...parseMixedBlock(block));
  }
  return nodes;
}

export function tokenizeInline(text) {
  const covered = [];
  MARKDOWN_BOLD.lastIndex = 0;
  let match;
  while ((match = MARKDOWN_BOLD.exec(text))) {
    covered.push({
      start: match.index,
      end: MARKDOWN_BOLD.lastIndex,
      value: match[1],
    });
  }

  AUTO_HIGHLIGHT.lastIndex = 0;
  while ((match = AUTO_HIGHLIGHT.exec(text))) {
    const start = match.index;
    const end = start + match[0].length;
    const overlaps = covered.some((range) => start < range.end && end > range.start);
    if (!overlaps && match[0].trim()) {
      covered.push({ start, end, value: match[0] });
    }
  }

  covered.sort((a, b) => a.start - b.start || b.end - a.end);
  const merged = [];
  for (const range of covered) {
    if (merged.some((existing) => range.start < existing.end && range.end > existing.start)) {
      continue;
    }
    merged.push(range);
  }

  const tokens = [];
  let cursor = 0;
  for (const range of merged) {
    if (range.start > cursor) {
      tokens.push({ bold: false, text: text.slice(cursor, range.start) });
    }
    tokens.push({ bold: true, text: range.value });
    cursor = range.end;
  }
  if (cursor < text.length) tokens.push({ bold: false, text: text.slice(cursor) });
  return tokens.filter((token) => token.text);
}
