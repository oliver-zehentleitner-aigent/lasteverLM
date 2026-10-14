import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SourceKind } from '../api/types'
import { ImageName } from './ImageName'

const render = (kind: SourceKind, previewUrl: string | null) =>
  renderToStaticMarkup(createElement(ImageName, { kind, previewUrl, label: 'name', title: 'name' }))

describe('ImageName', () => {
  it('shows a thumbnail for an image', () => {
    expect(render('image', 'https://storage.example/a.png?sig=1')).toContain('<img')
  })

  // the preview of these is no picture: loading it as one would fetch a
  // web page from the viewer's browser, or a presigned PDF as a broken image
  it.each<SourceKind>(['url', 'pdf', 'text'])('renders no <img> for %s', (kind) => {
    const html = render(kind, kind === 'url' ? 'https://en.wikipedia.org/wiki/Danube' : 'https://storage.example/a?sig=1')
    expect(html).not.toContain('<img')
    expect(html).toContain('name')
  })

  it('renders no <img> without a preview', () => {
    expect(render('image', null)).not.toContain('<img')
  })
})
