$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "Docker is required. Install Docker Desktop and ensure 'docker' is on PATH."
  exit 1
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $repoRoot "tiles-build"
$staticDir = Join-Path $repoRoot "work_tracker" "static" "tiles"
$pbfPath = Join-Path $buildDir "czech-republic-latest.osm.pbf"
$downloadUrl = "https://download.geofabrik.de/europe/czech-republic-latest.osm.pbf"
$outputPath = Join-Path $buildDir "cz.pmtiles"
$finalPath = Join-Path $staticDir "cz.pmtiles"
$planetilerImage = "ghcr.io/onthegomap/planetiler:latest"

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
New-Item -ItemType Directory -Path $staticDir -Force | Out-Null

if (-not (Test-Path $pbfPath)) {
  Write-Host "Downloading OSM extract for Czech Republic..."
  Invoke-WebRequest -Uri $downloadUrl -OutFile $pbfPath
}

Write-Host "Building PMTiles with Planetiler (this may take a while)..."
docker run --rm `
  -v "${buildDir}:/data" `
  $planetilerImage `
  --osm-path=/data/czech-republic-latest.osm.pbf `
  --output=/data/cz.pmtiles `
  --output-format=pmtiles `
  --openmaptiles `
  --download

if (-not (Test-Path $outputPath)) {
  Write-Error "Planetiler did not produce $outputPath"
  exit 1
}

Copy-Item -Force $outputPath $finalPath
$sizeMb = [math]::Round((Get-Item $finalPath).Length / 1MB, 2)
Write-Host "PMTiles ready at $finalPath ($sizeMb MB)"
