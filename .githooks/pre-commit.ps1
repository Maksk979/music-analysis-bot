# Pre-commit hook (Windows PowerShell variant) — runs fmt + clippy + tests
# before allowing a commit. Git on Windows uses the `pre-commit` shell script
# by default; this PowerShell file is a convenience for manual invocation:
#   pwsh .githooks\pre-commit.ps1

$ErrorActionPreference = "Stop"

Write-Host "[pre-commit] cargo fmt --check"
cargo fmt --all -- --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[pre-commit] cargo clippy"
cargo clippy --all-targets --quiet -- -D warnings
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[pre-commit] cargo test"
cargo test --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[pre-commit] OK"
