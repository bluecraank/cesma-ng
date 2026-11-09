import { describe, expect, it } from 'vitest'
import pkg from '../../package.json'
import { CHANGELOG, parseChangelog } from '@/changelog'

describe('changelog', () => {
  it('newest release matches package.json (SemVer)', () => {
    expect(CHANGELOG[0]?.version).toBe(pkg.version)
    for (const release of CHANGELOG) expect(release.version).toMatch(/^\d+\.\d+\.\d+$/)
  })

  it('every release has a date and at least one change', () => {
    for (const release of CHANGELOG) {
      expect(release.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(release.sections.flatMap((s) => s.items).length).toBeGreaterThan(0)
    }
  })

  it('parses Keep a Changelog markdown', () => {
    const parsed = parseChangelog(
      '# Changelog\n\n## [Unreleased]\n\n### Hinzugefügt\n\n- A\n\n## [1.2.0] - 2026-01-02\n\n### Behoben\n\n- B\n- C\n',
    )
    expect(parsed).toEqual([
      { version: 'Unreleased', date: null, sections: [{ title: 'Hinzugefügt', items: ['A'] }] },
      { version: '1.2.0', date: '2026-01-02', sections: [{ title: 'Behoben', items: ['B', 'C'] }] },
    ])
  })
})
