import type { MindmapNode } from '../api/types'

/** markmap takes a Markdown outline; the root becomes the heading, every
 *  child a nested list item. */
export function toMarkdown(node: MindmapNode, depth = 0): string {
  const line = depth === 0 ? `# ${node.label}` : `${'  '.repeat(depth - 1)}- ${node.label}`
  return [line, ...(node.children ?? []).map((c) => toMarkdown(c, depth + 1))].join('\n')
}
