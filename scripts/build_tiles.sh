#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop and ensure 'docker' is on PATH." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
build_dir="$repo_root/tiles-build"
static_dir="$repo_root/work_tracker/static/tiles"
pbf_path="$build_dir/czech-republic-latest.osm.pbf"
download_url="https://download.geofabrik.de/europe/czech-republic-latest.osm.pbf"
output_path="$build_dir/cz.pmtiles"
final_path="$static_dir/cz.pmtiles"
planetiler_image="ghcr.io/onthegomap/planetiler:latest"
openmaptiles_config="https://raw.githubusercontent.com/onthegomap/planetiler/main/resources/config/openmaptiles.yaml"

mkdir -p "$build_dir" "$static_dir"

if [ ! -f "$pbf_path" ]; then
  echo "Downloading OSM extract for Czech Republic..."
  curl -L "$download_url" -o "$pbf_path"
fi

echo "Building PMTiles with Planetiler (this may take a while)..."
docker run --rm \
  -v "$build_dir:/data" \
  "$planetiler_image" \
  --osm-path=/data/czech-republic-latest.osm.pbf \
  --output=/data/cz.pmtiles \
  --output-format=pmtiles \
  --config="$openmaptiles_config"

if [ ! -f "$output_path" ]; then
  echo "Planetiler did not produce $output_path" >&2
  exit 1
fi

cp "$output_path" "$final_path"

if size_bytes=$(stat -c%s "$final_path" 2>/dev/null); then
  :
elif size_bytes=$(stat -f%z "$final_path" 2>/dev/null); then
  :
else
  size_bytes=0
fi
size_mb=$(awk "BEGIN {printf \"%.2f\", ${size_bytes}/1024/1024}")
echo "PMTiles ready at $final_path (${size_mb} MB)"
