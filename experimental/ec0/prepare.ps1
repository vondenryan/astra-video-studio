param([ValidateSet('build','test','metadata')][string]$Action='build', [switch]$Release)
$ErrorActionPreference='Stop'
$repoRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$workspaceRoot=if ($env:ASTRA_WORKSPACE) { [IO.Path]::GetFullPath($env:ASTRA_WORKSPACE) } else { Join-Path $repoRoot 'workspace' }
$ecRoot=Join-Path $workspaceRoot 'ec0'
$env:ASTRA_WORKSPACE=$workspaceRoot
New-Item -ItemType Directory -Force -Path "$ecRoot\downloads","$ecRoot\evidence","$ecRoot\temp" | Out-Null
$env:CARGO_HOME="$ecRoot\cargo-home"
$env:RUSTUP_HOME="$ecRoot\rustup-home"
$env:CARGO_TARGET_DIR="$ecRoot\target"
$env:CARGO_NET_GIT_FETCH_WITH_CLI='true'
$env:RUSTUP_INIT_SKIP_PATH_CHECK='yes'
$env:TEMP="$ecRoot\temp"
$env:TMP=$env:TEMP
$rustup=Join-Path $env:CARGO_HOME 'bin\rustup.exe'
if (-not (Test-Path -LiteralPath $rustup)) {
    $installer=Join-Path $ecRoot 'downloads\rustup-init-1.28.2.exe'
    if (-not (Test-Path -LiteralPath $installer)) {
        Invoke-WebRequest -Uri 'https://static.rust-lang.org/rustup/archive/1.28.2/x86_64-pc-windows-msvc/rustup-init.exe' -OutFile $installer
    }
    $expected='88d8258dcf6ae4f7a80c7d1088e1f36fa7025a1cfd1343731b4ee6f385121fc0'
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Rustup checksum mismatch' }
    & $installer -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-msvc --default-toolchain 1.95.0
    if ($LASTEXITCODE -ne 0) { throw 'Private Rust installation failed' }
}
$cargo=Join-Path $env:CARGO_HOME 'bin\cargo.exe'
$manifest=Join-Path $PSScriptRoot 'worker\Cargo.toml'
# Use the private toolchain explicitly; do not depend on caller cwd overrides.
if ($Action -eq 'metadata') {
    $metadataDir=Join-Path $ecRoot ('evidence\metadata-'+[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $metadataDir | Out-Null
    & $cargo +1.95.0 metadata --locked --manifest-path $manifest --format-version 1 --filter-platform x86_64-pc-windows-msvc 1> "$metadataDir\cargo-metadata.json" 2> "$metadataDir\cargo-metadata.log"
    if ($LASTEXITCODE -ne 0) { throw 'Locked Cargo metadata failed; inspect retained log' }
    & (Join-Path $repoRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'check_dependencies.py') "$metadataDir\cargo-metadata.json" "$metadataDir\dependency-closure.json"
} else {
    [string[]]$profileArgs=@()
    if ($Release) { $profileArgs=@('--release') }
    & $cargo +1.95.0 $Action --locked --manifest-path $manifest -j 2 @profileArgs
}
if ($LASTEXITCODE -ne 0) { throw "EC0 $Action failed; no automatic retry" }
