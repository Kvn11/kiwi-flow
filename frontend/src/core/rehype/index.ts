import type { Element, Root, ElementContent } from "hast";
import type { StreamdownProps } from "streamdown";
import { visit } from "unist-util-visit";
import type { BuildVisitor } from "unist-util-visit";

type PluggableList = NonNullable<StreamdownProps["rehypePlugins"]>;

const CJK_TEXT_RE =
  /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

const SPLIT_TARGET_TAGS = new Set([
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "li",
  "strong",
]);

// Constructing Intl.Segmenter is expensive (tens of ms in some engines). Build
// once per process and reuse — it is stateless across segment() calls.
let _segmenter: Intl.Segmenter | null = null;
function getSegmenter() {
  _segmenter ??= new Intl.Segmenter("zh", { granularity: "word" });
  return _segmenter;
}

export function rehypeSplitWordsIntoSpans() {
  return (tree: Root) => {
    visit(tree, "element", ((node: Element) => {
      if (!SPLIT_TARGET_TAGS.has(node.tagName) || !node.children) {
        return;
      }
      // Cheap pre-check: only walk children when at least one is text.
      let hasText = false;
      for (const child of node.children) {
        if (child.type === "text") {
          hasText = true;
          break;
        }
      }
      if (!hasText) return;

      const segmenter = getSegmenter();
      const newChildren: Array<ElementContent> = [];
      for (const child of node.children) {
        if (child.type !== "text") {
          newChildren.push(child);
          continue;
        }
        if (CJK_TEXT_RE.test(child.value)) {
          newChildren.push(child);
          continue;
        }
        const segments = segmenter.segment(child.value);
        for (const segment of segments) {
          const word = segment.segment;
          if (!word) continue;
          newChildren.push({
            type: "element",
            tagName: "span",
            properties: { className: "animate-fade-in" },
            children: [{ type: "text", value: word }],
          });
        }
      }
      node.children = newChildren;
    }) as BuildVisitor<Root, "element">);
  };
}

const EMPTY_PLUGINS: PluggableList = [];
const SPLIT_PLUGINS: PluggableList = [rehypeSplitWordsIntoSpans];

// The fade-in animation is only meaningful for content actively being streamed.
// Applying it to settled messages costs us a per-text-node walk that emits a
// <span> per word for no visible benefit, so callers should pass `enabled` only
// for the currently-streaming message (not the whole conversation).
export function useRehypeSplitWordsIntoSpans(enabled = true) {
  return enabled ? SPLIT_PLUGINS : EMPTY_PLUGINS;
}
