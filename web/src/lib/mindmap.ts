import type { MindmapNode } from '../api/types'

/** markmap takes a Markdown outline; the root becomes the heading, every
 *  child a nested list item. A label is one line: a line break in the
 *  model's text would otherwise start a node of its own. */
export function toMarkdown(node: MindmapNode, depth = 0, marks: (n: MindmapNode) => string = () => ''): string {
  const label = node.label.replace(/\s+/g, ' ').trim() + marks(node)
  const line = depth === 0 ? `# ${label}` : `${'  '.repeat(depth - 1)}- ${label}`
  return [line, ...(node.children ?? []).map((c) => toMarkdown(c, depth + 1, marks))].join('\n')
}

/** A node as markmap's transformer returns it: `content` is HTML. */
export interface MarkmapNode {
  content: string
  children?: MarkmapNode[]
}

/** markmap renders each node's `content` as HTML (innerHTML) and its
 *  transformer passes raw HTML in the Markdown through, so the labels,
 *  which come from the model, are cleaned node by node before rendering. */
export function cleanTree<T extends MarkmapNode>(node: T, clean: (html: string) => string): T {
  return { ...node, content: clean(node.content), children: node.children?.map((c) => cleanTree(c, clean)) }
}
