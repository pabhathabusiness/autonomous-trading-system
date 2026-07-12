# ROLLBACK.md — upgrade/grading-news safety net

Created 2026-07-11 (Phase 0), before any Phase 1+ change. Two independent
restore paths exist; the server snapshot tables are the primary one.

## What was snapshotted

| Copy | Where | Contents |
|---|---|---|
| **Primary: snapshot tables** | live DB `data/trading_system.db` on the droplet | `paper_trades_bak_20260711` (78 rows), `proposals_bak_20260711` (284 rows) — verified row-for-row counts at creation |
| **Secondary: JSON dumps** | this repo, `./backups/paper_trades_bak_20260711.json` (78×38) and `./backups/proposals_bak_20260711.json` (284×23) — kept **untracked** (backups/ is gitignored; data doesn't belong in git) |

The upgrade only *adds* columns / writes currently-NULL columns, so restoring is
"put the old values back", never "recover deleted rows". Still, full-table
restore commands are below.

---

## A. Restore the DB from the snapshot tables (primary path)

SSH to the droplet (`ssh root@159.223.158.154`), then:

```bash
cd /home/trading/autonomous-trading-system
sudo systemctl stop trading    # stop writers first

sudo -u trading .venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect('data/trading_system.db')
for t in ("paper_trades", "proposals"):
    bak = f"{t}_bak_20260711"
    n = c.execute(f"SELECT count(*) FROM {bak}").fetchone()[0]
    assert n > 0, f"{bak} is empty -- ABORT, use path B"
    c.execute(f"DROP TABLE {t}")
    c.execute(f"CREATE TABLE {t} AS SELECT * FROM {bak}")
    c.commit()
    print(t, "restored:", c.execute(f"SELECT count(*) FROM {t}").fetchone()[0], "rows")
PY

sudo systemctl start trading
sudo systemctl status trading --no-pager
```

Notes:
- `CREATE TABLE ... AS SELECT` does not recreate the `UNIQUE(proposal_id)` /
  PK constraints, but the app's `Database.init_schema()` never drops data and
  the code paths use plain INSERT/SELECT/UPDATE — acceptable for an emergency
  restore. For a constraint-perfect restore, instead run the app's schema first
  (`CREATE TABLE IF NOT EXISTS` from `src/database.py`) on a fresh file and
  `INSERT INTO ... SELECT` from the snapshot tables.
- The snapshot tables are left in place after restore (they're cheap; drop them
  only when the upgrade is signed off: `DROP TABLE paper_trades_bak_20260711;`).

## B. Restore from the JSON dumps (if the snapshot tables are gone)

From this machine (dumps live in `./backups/`):

```bash
# copy the dumps up
scp -i ~/.ssh/droplet_deploy backups/paper_trades_bak_20260711.json backups/proposals_bak_20260711.json \
    root@159.223.158.154:/home/trading/autonomous-trading-system/

# then on the droplet:
cd /home/trading/autonomous-trading-system
sudo systemctl stop trading
sudo chown trading:trading paper_trades_bak_20260711.json proposals_bak_20260711.json
sudo -u trading .venv/bin/python - <<'PY'
import sqlite3, json
c = sqlite3.connect('data/trading_system.db')
for t in ("paper_trades", "proposals"):
    rows = json.load(open(f"{t}_bak_20260711.json"))
    cols = list(rows[0].keys())
    c.execute(f"DROP TABLE IF EXISTS {t}")
    c.execute(f"CREATE TABLE {t} ({', '.join(cols)})")
    c.executemany(
        f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(':'+k for k in cols)})", rows)
    c.commit()
    print(t, "restored:", c.execute(f"SELECT count(*) FROM {t}").fetchone()[0], "rows")
PY
sudo systemctl start trading
```

(Same constraint caveat as path A.)

## C. Revert the code branch

Nothing from this upgrade merges to `main` until sign-off, so:

```bash
# local: throw the branch away entirely
git checkout main
git branch -D upgrade/grading-news
git push origin --delete upgrade/grading-news   # only if it was ever pushed

# or: keep the branch but reset it to a specific phase commit
git log --oneline            # find the last good phase commit
git reset --hard <sha>
```

The live server deploys only what we explicitly ship to it; if a bad phase was
already shipped, redeploy `main` (tar-over-ssh of the changed files or
`git reset --hard origin/main` on the server checkout) and restart:

```bash
sudo systemctl restart trading && sudo journalctl -u trading -f
```

## D. Verify after any restore

```bash
curl -s -u USER:PASS http://127.0.0.1:8000/api/health
# and in the DB:
# select count(*) from paper_trades;   -- expect 78 (pre-upgrade) or current count
# select count(*) from proposals;     -- expect 284 (pre-upgrade) or current count
```
