# SNF Ownership Map

An interactive map of every Medicare skilled nursing facility in the US, with owner, parent-chain and
management-company views. Data comes from three public CMS files and refreshes itself every month.

* **Map**: every building, colored by its chain's average star rating. Click a pin to see ownership and
  jump to every building the same company owns or manages.
* **Owners**: sortable pivot of parent chains, 5%+ owners and management companies.
* **States**: roll-up by state.

The site is three static files (`index.html`, `data.json`, `states.json`). No server, no database.

## Put it online (GitHub Pages)

1. Create a new **public** repository on GitHub and upload everything in this folder, including the
   hidden `.github` folder.
2. In the repository go to **Settings > Pages**. Under **Build and deployment**, set **Source** to
   **GitHub Actions**.
3. Go to the **Actions** tab. The "Refresh data and deploy" workflow starts by itself after your first
   upload. When it turns green, your site is live at `https://YOUR-USERNAME.github.io/REPO-NAME/`.

## How the data stays fresh

`.github/workflows/site.yml` runs on the 5th of every month. It downloads the latest CMS files,
rebuilds `data.json`, saves it to the repo and redeploys the site. You can also run it any time from
**Actions > Refresh data and deploy > Run workflow**.

If a refresh fails, the site keeps showing the last good data. The log in the Actions tab says what
went wrong. The usual cause is that CMS moved a file. Fix it by pasting the new download link into
`sources.json` (or by setting the `ENROLLMENTS_URL`, `OWNERS_URL`, `CHAIN_URL` environment variables).
`scripts/build_data.py` refuses to write `data.json` if the numbers look wrong (for example fewer than
10,000 facilities), so a bad download cannot replace good data.

## Run it on your own computer

```
pip install -r requirements.txt
python scripts/refresh.py                 # download and rebuild data.json
python -m http.server 8000                # then open http://localhost:8000
```

To rebuild from CSVs you already have, put them in `data/raw/` (file names must contain "Enroll",
"Owners" and "Chain") and run `python scripts/refresh.py --no-download`.

## What the data does and does not show

* Star ratings are **chain averages** from the CMS Chain Performance file, not per-building ratings.
  Independent buildings show no rating.
* Pins sit at the center of each building's ZIP code with a small fixed nudge, so they are close but
  not exact. Adding the CMS Provider Information file (`4pq5-n9py`) would give exact coordinates and
  per-building ratings.
* "Owners 5%+" are companies and people with a direct or indirect ownership interest of 5% or more.
  Only owners and managers with two or more buildings are included.
* This project is not affiliated with or endorsed by CMS.

## Files

| File | What it is |
| --- | --- |
| `index.html` | The whole app |
| `data.json` | Joined facility, chain and owner data (rebuilt monthly) |
| `states.json` | State outlines for the base map |
| `scripts/refresh.py` | Downloads the CMS files and runs the build |
| `scripts/build_data.py` | Joins the files into `data.json` |
| `sources.json` | Fallback download links for the three CMS files |
| `.github/workflows/site.yml` | Monthly refresh and deploy |
