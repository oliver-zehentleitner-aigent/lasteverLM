/** Where a hover preview goes: to the right of its anchor when it fits,
 *  else to the left, else over it; vertically centred on the anchor and
 *  kept inside the viewport with a margin. */
export function previewPosition(
  anchor: { left: number; right: number; top: number; bottom: number },
  viewport: { width: number; height: number },
  size: { width: number; height: number },
  gap = 8,
  margin = 8,
): { left: number; top: number } {
  let left = anchor.right + gap
  if (left + size.width > viewport.width - margin) left = anchor.left - gap - size.width
  if (left < margin) left = Math.max(margin, Math.min(viewport.width - margin - size.width, anchor.left))
  const centre = (anchor.top + anchor.bottom) / 2
  const top = Math.max(margin, Math.min(viewport.height - margin - size.height, centre - size.height / 2))
  return { left: Math.round(left), top: Math.round(top) }
}
