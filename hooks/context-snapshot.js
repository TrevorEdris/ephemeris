#!/usr/bin/env node
/**
 * Context Snapshot - PreCompact Hook
 * Before context compaction, saves a CONTEXT_SNAPSHOT.md to the current session dir.
 * Captures phase, key headings, and summary from SESSION/DISCOVERY/PLAN.md.
 *
 * @fotw-hook {"event":"PreCompact","matcher":"","description":"Saves context snapshot before compaction"}
 *
 * Setup in .claude/settings.json:
 * {
 *   "hooks": {
 *     "PreCompact": [{
 *       "hooks": [{ "type": "command", "command": "node ~/.claude/hooks/context-snapshot.js" }]
 *     }]
 *   }
 * }
 */

const fs = require('fs');
const path = require('path');

const DEFAULT_SESSION_ROOT = path.join(process.env.HOME, 'src', '.ai', 'sessions');
const SESSION_FILES = ['SESSION.md', 'DISCOVERY.md', 'PLAN.md'];

function findTodaySessionDir(sessionRoot) {
  const today = new Date().toISOString().slice(0, 10);
  try {
    const entries = fs.readdirSync(sessionRoot)
      .filter(e => e.startsWith(today + '_'))
      .sort();
    if (entries.length === 0) return null;
    return path.join(sessionRoot, entries[entries.length - 1]); // last = most recent alphabetically
  } catch {
    return null;
  }
}

function inferPhase(sessionDir) {
  const has = (f) => fs.existsSync(path.join(sessionDir, f));
  if (has('PLAN.md')) return 'implement';
  if (has('DISCOVERY.md')) return 'plan';
  if (has('SESSION.md')) return 'discover';
  return null;
}

function extractHeadings(content) {
  const headings = [];
  for (const line of content.split('\n')) {
    const m = line.match(/^##\s+(.+)/);
    if (m) headings.push(m[1].trim());
  }
  return headings;
}

function readFileSafe(filePath) {
  try { return fs.readFileSync(filePath, 'utf8'); } catch { return null; }
}

function createSnapshot(sessionRoot = DEFAULT_SESSION_ROOT) {
  const sessionDir = findTodaySessionDir(sessionRoot);
  if (!sessionDir) return { phase: null, snapshot: null };

  const phase = inferPhase(sessionDir);
  if (!phase) return { phase: null, snapshot: null };

  const sections = [];
  const timestamp = new Date().toISOString();
  sections.push(`# Context Snapshot`);
  sections.push(`> Generated: ${timestamp}`);
  sections.push(`> Phase: **${phase}**`);
  sections.push(`> Session: \`${path.basename(sessionDir)}\``);
  sections.push('');

  for (const filename of SESSION_FILES) {
    const content = readFileSafe(path.join(sessionDir, filename));
    if (!content) continue;

    const headings = extractHeadings(content);
    sections.push(`## ${filename}`);
    if (headings.length > 0) {
      sections.push(`Sections: ${headings.join(', ')}`);
    }
    // Include first ~30 lines of content as summary
    const lines = content.split('\n').slice(0, 30);
    sections.push('');
    sections.push('```');
    sections.push(lines.join('\n'));
    sections.push('```');
    sections.push('');
  }

  const snapshot = sections.join('\n');
  const snapshotPath = path.join(sessionDir, 'CONTEXT_SNAPSHOT.md');
  fs.writeFileSync(snapshotPath, snapshot);

  return { phase, snapshot, sessionDir };
}

async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;

  try {
    createSnapshot();
  } catch {
    // PreCompact cannot block, just log and continue
  }
  console.log('{}');
}

if (require.main === module) {
  main();
} else {
  module.exports = { createSnapshot, findTodaySessionDir, inferPhase, extractHeadings };
}
