#!/usr/bin/env node
/**
 * Session Reminder - UserPromptSubmit Hook
 * Reminds the agent to create a session directory if one doesn't exist for today.
 * Lightweight: single readdirSync + startsWith check.
 *
 * @fotw-hook {"event":"UserPromptSubmit","matcher":"","description":"Reminds agent to create session directory"}
 *
 * Setup in .claude/settings.json:
 * {
 *   "hooks": {
 *     "UserPromptSubmit": [{
 *       "hooks": [{ "type": "command", "command": "node ~/.claude/hooks/session-reminder.js" }]
 *     }]
 *   }
 * }
 */

const fs = require('fs');
const path = require('path');

const DEFAULT_SESSION_ROOT = path.join(process.env.HOME, 'src', '.ai', 'sessions');

function checkSession(sessionRoot = DEFAULT_SESSION_ROOT) {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

  try {
    const entries = fs.readdirSync(sessionRoot);
    const hasToday = entries.some(e => e.startsWith(today + '_'));
    if (hasToday) return { remind: false, message: '' };
  } catch {
    // Directory doesn't exist — definitely need a reminder
  }

  return {
    remind: true,
    message: `REMINDER: No session directory found for ${today}. Create one at ${sessionRoot}/${today}_<JIRA>_<TITLE_SLUG>/ and register it for the status line.`,
  };
}

async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;

  try {
    const result = checkSession();
    if (result.remind) {
      return console.log(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'UserPromptSubmit',
          additionalContext: result.message,
        },
      }));
    }
    console.log('{}');
  } catch {
    console.log('{}');
  }
}

if (require.main === module) {
  main();
} else {
  module.exports = { checkSession };
}
