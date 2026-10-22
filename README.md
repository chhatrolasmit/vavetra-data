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
