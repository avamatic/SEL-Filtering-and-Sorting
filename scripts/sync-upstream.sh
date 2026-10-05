#!/usr/bin/env bash
set -euo pipefail

# The optional URL also allows offline tests against a local upstream repository.
upstream_url=${1:-https://github.com/Tam-Taro/SEL-Filtering-and-Sorting.git}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ $(git branch --show-current) != main || -n $(git status --porcelain) ]]; then
  echo 'Sync requires a clean checkout of main.' >&2
  exit 1
fi

git fetch --no-tags origin main
git merge --ff-only refs/remotes/origin/main
expected_remote=$(git rev-parse refs/remotes/origin/main)
if [[ $(git rev-parse HEAD) != "$expected_remote" ]]; then
  echo 'Local main has unpublished commits; refusing to publish them.' >&2
  exit 1
fi

git fetch --no-tags "$upstream_url" main
upstream_revision=$(git rev-parse FETCH_HEAD)
if git merge-base --is-ancestor "$upstream_revision" HEAD; then
  python3 "$script_dir/validate-trek-patch.py"
  echo 'Upstream is already included; nothing to publish.'
  exit 0
fi

if ! git rebase "$upstream_revision"; then
  git rebase --abort
  echo 'Upstream rebase conflicted. The published fork has not changed.' >&2
  exit 1
fi

python3 "$script_dir/validate-trek-patch.py"

# Rebasing rewrites the fork commits. The explicit lease rejects any change
# made to remote main since this run fetched it, even after background fetches.
git push "--force-with-lease=refs/heads/main:$expected_remote" origin HEAD:refs/heads/main
echo "Published upstream $upstream_revision with the fork patches reapplied."
