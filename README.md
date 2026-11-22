# bridalseamstress.com.au

Static directory site. `build.py` turns `data/master.json` (export of the master Google Sheet, {range, values} format) into `site/public/`.
Listing photos go in `data/photos/` and are named in the sheet's `photos` column.

Pushing to `main` builds and deploys to the Cloudflare Pages project `bridalseamstress` (see `.github/workflows/deploy.yml`).
Repo secrets needed: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLAIMS_KV_ID`.

`site/functions/api/claim.js` is the claim form handler. `mailer/` is the separate Worker `bridalseamstress-mailer` (deployed by hand, not by this workflow).
