import { describe, expect, it } from 'vitest'
import { clusterGap, shortCommit, tagVersion, versionLine } from './build'

describe('build line', () => {
  it('joins version and short commit, skipping unknown parts', () => {
    expect(versionLine('0.6.1', '5e320ae9f0c1')).toBe('lasteverLM 0.6.1 · 5e320ae')
    expect(versionLine('0.6.1', 'unknown')).toBe('lasteverLM 0.6.1')
    expect(versionLine(null, 'abcdef0123')).toBe('lasteverLM · abcdef0')
    expect(versionLine('unknown', null)).toBeNull()
    expect(shortCommit(undefined)).toBeNull()
  })
})

describe('clusterGap', () => {
  it('tells a local run from a missing read role', () => {
    expect(clusterGap({ cluster: false, pods: [], deployments: [] })).toBe('no-cluster')
    expect(clusterGap({ cluster: true, pods: [], deployments: [] })).toBe('no-role')
    expect(clusterGap({ cluster: true, pods: [{}], deployments: [] })).toBeNull()
  })
})

describe('tagVersion', () => {
  it('keeps the tag\'s own v and adds one where it is missing', () => {
    expect(tagVersion('v0.18.3')).toBe('v0.18.3')
    expect(tagVersion('0.8.2')).toBe('v0.8.2')
  })
})
