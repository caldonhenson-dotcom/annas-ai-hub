#!/bin/bash
# Ralph Loop — Autonomous coding agent
# Grinds through prd.json stories in a fresh context each iteration
# Usage: bash ralph.sh [--max-loops N]
#
# Prerequisites:
#   1. Generate prd.json with /ralph-prep or manually
#   2. Ensure claude CLI is available
#   3. Run from project root

set -euo pipefail

MAX_LOOPS="${1:-50}"
LOOP_COUNT=0
PRD_FILE="prd.json"
PROGRESS_FILE="progress.txt"
PROJECT_DIR="$(pwd)"

# Colours
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Ralph Loop Starting ===${NC}"
echo "Project: ${PROJECT_DIR}"
echo "Max loops: ${MAX_LOOPS}"
echo "PRD: ${PRD_FILE}"
echo ""

# Verify prd.json exists
if [ ! -f "$PRD_FILE" ]; then
  echo -e "${RED}Error: ${PRD_FILE} not found. Run /ralph-prep first.${NC}"
  exit 1
fi

# Initialise progress file if it doesn't exist
if [ ! -f "$PROGRESS_FILE" ]; then
  echo "# Ralph Loop Progress" > "$PROGRESS_FILE"
  echo "Started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$PROGRESS_FILE"
  echo "---" >> "$PROGRESS_FILE"
fi

while [ $LOOP_COUNT -lt $MAX_LOOPS ]; do
  LOOP_COUNT=$((LOOP_COUNT + 1))
  echo -e "${YELLOW}--- Loop ${LOOP_COUNT}/${MAX_LOOPS} ---${NC}"

  # Check if all stories are done
  REMAINING=$(cat "$PRD_FILE" | python3 -c "
import json, sys
prd = json.load(sys.stdin)
remaining = [s for s in prd.get('stories', []) if s.get('status') != 'done']
print(len(remaining))
" 2>/dev/null || echo "error")

  if [ "$REMAINING" = "0" ]; then
    echo -e "${GREEN}All stories complete!${NC}"
    echo "Completed: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$PROGRESS_FILE"
    break
  fi

  if [ "$REMAINING" = "error" ]; then
    echo -e "${RED}Error reading prd.json${NC}"
    exit 1
  fi

  echo "Stories remaining: ${REMAINING}"

  # Build the prompt for this iteration
  PROMPT="You are an autonomous coding agent running in Ralph Loop mode (iteration ${LOOP_COUNT}).

READ these files first:
1. prd.json — the product requirements with user stories
2. progress.txt — what has been done so far
3. CLAUDE.md — project conventions

YOUR TASK:
1. Find the FIRST story in prd.json with status 'not-done' that has all dependencies met (depends_on stories are 'done')
2. Implement that ONE story completely
3. Run 'npx tsc --noEmit' to verify no type errors
4. Update the story status to 'done' in prd.json
5. Append a summary to progress.txt with: story ID, what was done, files changed
6. Git commit the changes with a descriptive message

RULES:
- Only work on ONE story per iteration
- If you encounter an error you cannot fix, update progress.txt with the blocker and exit
- Do not modify stories you are not working on
- Follow existing code patterns in the project
- British English in all copy and comments

After completing the story, exit. The loop will restart you with fresh context."

  # Run Claude with fresh context (dangerously-skip-permissions for unattended mode)
  echo "$PROMPT" | claude --dangerously-skip-permissions -p 2>&1 | tee -a "ralph-log-${LOOP_COUNT}.txt"

  # Brief pause between iterations
  sleep 2

  echo -e "${GREEN}Loop ${LOOP_COUNT} complete${NC}"
  echo "" >> "$PROGRESS_FILE"
done

echo -e "${GREEN}=== Ralph Loop Finished ===${NC}"
echo "Total iterations: ${LOOP_COUNT}"
echo "Check progress.txt for details"
