# US Bridal Seamstress directory

Same site as the AU one, for US cities. Nothing here is live yet.

- `patch_build.py` makes `build_us.py` from the AU `build.py` at build time, so AU features (verified, featured, photos, claim form) carry over. If the AU build.py changes a line this script patches, the build stops and names the line.
- `data/master.json` is the US master sheet export (same columns as AU). `data/photos/` holds US listing photos. No blog yet, so the Guides links are hidden.
- `site/functions/api/claim.js` is the AU claim handler, marking requests "USA". It shares the AU KV and mailer Worker.
- `.github/workflows/deploy-us.yml` deploys to the Pages project `bridalseamstress-us`. It stays off until the repo variable `US_DEPLOY` is `true`. Variables: `US_HOST` (the domain, e.g. bridalseamstresses.com), `US_GA_ID` (US GA4 measurement ID).

Local preview: `python3 us/patch_build.py build.py us/build_us.py && python3 us/build_us.py us/data/master.json us/site/public --preview`
