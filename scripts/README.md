# PMTiles build scripts

These scripts are used to build Czech OpenMapTiles PMTiles for ArboMap.

Output:
- cz.pmtiles (NOT committed to git)

Typical workflow:
1. Run build script (Planetiler / Tippecanoe).
2. Optionally run UTF-8 conversion.
3. Copy resulting cz.pmtiles to:
   work_tracker/static/tiles/cz.pmtiles
4. Deploy cz.pmtiles separately (scp/rsync), not via git.

Reason:
- PMTiles files are ~600+ MB and must not be stored in git.
