# vavetra-data

Data files for the **Vavetra Yard** Android app.

## yards.tsv

Position of every agricultural market yard (APMC) in India. The app checks this file once a month,
so new yards get a position without a new app version.

One yard per line, tab separated:

| column | meaning |
|---|---|
| 1 | state code (GJ, MH, RJ …) |
| 2 | yard name key (lower case letters only, without "APMC", "Market", "(F&V)") |
| 3 | latitude |
| 4 | longitude |
| 5 | 1 = town position, 0 = only district position (approximate) |

Rules the app checks before using a new file: at least 3,000 lines, every position inside India.
A wrong or short file is ignored and the app keeps the copy it has.

Sources: yard list from Agmarknet; place positions from Survey of India place names
(via datameet / ramSeraph indian_admin_boundaries, CC0) and GeoNames (CC BY 4.0).

## Monthly update (automatic)

On the 1st of every month GitHub runs `.github/workflows/update-yards.yml`:

1. It downloads the list of all yards from Agmarknet.
2. New yards get a position (OpenStreetMap, checked to be inside their district; if the town is not
   found, the district's position is used and marked approximate). Yards that left the list are removed.
3. `yards.tsv` is rebuilt from `yards_src.txt` and saved. The app picks it up within a month.

If Agmarknet does not answer, or sends a much shorter list than last month, nothing is changed and the
run fails; GitHub sends an e-mail. Start it by hand: Actions → Monthly yard update → Run workflow.

To fix a wrong position by hand: change its line in `yards_src.txt` (state|district|yard|lat|lng|quality)
and run the workflow once.
