import test from "node:test";
import assert from "node:assert/strict";
import { parseAnswer, splitDenseParagraph, tokenizeInline } from "./formatAnswer.js";

test("splits a dense financial paragraph into readable blocks", () => {
  const text =
    "The Power Unit cost cap for 2026 is $2.15 million (₹204.23 million / £1.59 million) as outlined in Article E2.3.1.b. Additionally, there are specific homologation constraints in the regulations.";
  const parts = splitDenseParagraph(text);
  assert.ok(parts.length >= 2);
  assert.match(parts[0], /\$2\.15 million/);
});

test("parses markdown headings, lists, and paragraphs", () => {
  const nodes = parseAnswer(
    "## 2026 Cost Cap\n\nThe cap is **$135 million**.\n\n- Power Unit limit\n- Aerodynamic testing"
  );
  assert.equal(nodes[0].type, "heading");
  assert.equal(nodes[0].text, "2026 Cost Cap");
  assert.equal(nodes[1].type, "paragraph");
  assert.equal(nodes[2].type, "list");
  assert.equal(nodes[2].items.length, 2);
});

test("bolds markdown and money figures", () => {
  const tokens = tokenizeInline(
    "The cap is **$2.15 million** and also ₹204.23 million under Article E2.3.1.b."
  );
  const bold = tokens.filter((t) => t.bold).map((t) => t.text);
  assert.ok(bold.some((t) => t.includes("$2.15 million")));
  assert.ok(bold.some((t) => t.includes("₹204.23 million")));
  assert.ok(bold.some((t) => t.includes("Article E2.3.1.b")));
});

test("turns race classification labels into headings and list items", () => {
  const nodes = parseAnswer(
    "The results for the 2021 Monaco Grand Prix are as follows:\n\nClassified finishers (18):\n1. Max Verstappen (Red Bull) - 1:38:56.820\n2. Carlos Sainz (Ferrari) - +8.968\n\nDid not finish (2):\n- Valtteri Bottas (Mercedes)"
  );
  const headings = nodes.filter((n) => n.type === "heading").map((n) => n.text);
  assert.ok(headings.some((h) => h.startsWith("Classified finishers")));
  assert.ok(headings.some((h) => h.startsWith("Did not finish")));
  assert.ok(nodes.some((n) => n.type === "list" && n.ordered));
});
