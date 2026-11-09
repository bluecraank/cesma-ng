/**
 * Patch notes, parsed from CHANGELOG.md (Keep a Changelog) at build time.
 * The newest release must match the version in package.json (checked by a unit test).
 */
import changelogText from '../../CHANGELOG.md?raw'

export interface ReleaseSection {
  title: string // e.g. "Hinzugefügt", "Behoben"
  items: string[]
}

export interface Release {
  version: string
  date: string | null
  sections: ReleaseSection[]
}

export const APP_VERSION: string = __APP_VERSION__

const RELEASE = /^## \[([^\]]+)\](?:\s+-\s+(\d{4}-\d{2}-\d{2}))?/
const SECTION = /^### (.+)/
const ITEM = /^[-*] (.+)/

export function parseChangelog(text: string): Release[] {
  const releases: Release[] = []
  let release: Release | undefined
  let section: ReleaseSection | undefined
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    let match: RegExpMatchArray | null
    if ((match = line.match(RELEASE))) {
      release = { version: match[1] ?? '', date: match[2] ?? null, sections: [] }
      section = undefined
      releases.push(release)
    } else if (release && (match = line.match(SECTION))) {
      section = { title: match[1] ?? '', items: [] }
      release.sections.push(section)
    } else if (section && (match = line.match(ITEM))) {
      section.items.push(match[1] ?? '')
    }
  }
  return releases
}

/** Released versions, newest first ("Unreleased" is left out). */
export const CHANGELOG: Release[] = parseChangelog(changelogText).filter(
  (r) => r.version.toLowerCase() !== 'unreleased',
)
