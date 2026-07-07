# Deploying to the DigitalOcean server (beginner walk-through)

Target: Ubuntu server at **159.223.158.154**, reachable at **pabs-trading.duckdns.org**.
Run these **on the server** (after `ssh root@159.223.158.154`). Go one block at a
time and read the note above each. Nothing here contains secrets — you type your
real keys only in Step 6.

Prereq: `nslookup pabs-trading.duckdns.org` must return **159.223.158.154** first.

---

## 1. Update the system + install what we need
```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx ufw
```

## 2. Firewall — allow SSH + web, then enable (order matters: SSH first!)
```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status
```
> ⚠️ Do NOT enable the firewall before allowing OpenSSH, or you can lock
> yourself out of the server.

## 3. Create a non-root user to run the app
```bash
adduser --disabled-password --gecos "" trading
```

## 4. Get the code (private repo -> needs a GitHub token)
Create a **fine-grained token** at https://github.com/settings/tokens?type=beta
(Repository access: only `autonomous-trading-system`; Permission: Contents = Read).
Then:
```bash
sudo -u trading git clone https://YOUR_GITHUB_TOKEN@github.com/pabhathabusiness/autonomous-trading-system.git /home/trading/autonomous-trading-system
```
> The token is used once for the clone. To avoid leaving it saved on the server,
> after cloning run:
> `sudo -u trading git -C /home/trading/autonomous-trading-system remote set-url origin https://github.com/pabhathabusiness/autonomous-trading-system.git`

## 5. Python environment + dependencies
```bash
cd /home/trading/autonomous-trading-system
sudo -u trading python3 -m venv .venv
sudo -u trading .venv/bin/pip install --upgrade pip
sudo -u trading .venv/bin/pip install -r requirements.txt
```

## 6. Create the real config (YOUR secrets go here, on the server only)
```bash
sudo -u trading cp config/config.example.json config/config.json
sudo -u trading nano config/config.json
```
In nano, fill in:
- `alpaca.enabled`: true, and your **new** `alpaca_key` / `alpaca_secret`
- `auth.username` / `auth.password`: pick a **fresh** login for you and your dad
Save: `Ctrl+O`, Enter, then `Ctrl+X`.
> This file is gitignored — it will never be committed.

## 7. Quick test that it starts (Ctrl+C to stop after you see "Uvicorn running")
```bash
sudo -u trading .venv/bin/python -m src.main serve --host 127.0.0.1 --port 8000
```

## 8. Install the always-on service (systemd)
```bash
cp deploy/trading.service /etc/systemd/system/trading.service
systemctl daemon-reload
systemctl enable --now trading
systemctl status trading --no-pager
```

## 9. Put nginx in front
```bash
cp deploy/nginx-trading.conf /etc/nginx/sites-available/trading
ln -sf /etc/nginx/sites-available/trading /etc/nginx/sites-enabled/trading
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```
Now http://pabs-trading.duckdns.org should load (with the login prompt).

## 10. Turn on free HTTPS (Let's Encrypt)
```bash
certbot --nginx -d pabs-trading.duckdns.org --non-interactive --agree-tos -m pabhatha.business@gmail.com --redirect
```
Now **https://pabs-trading.duckdns.org** works and the login is encrypted.

---

## Updating later (after you push new code to GitHub)
```bash
cd /home/trading/autonomous-trading-system
sudo -u trading git pull
sudo -u trading .venv/bin/pip install -r requirements.txt
systemctl restart trading
```
Your paper-trade history in `data/` is untouched by updates.

## Handy checks
- App logs: `journalctl -u trading -f`
- Restart app: `systemctl restart trading`
- Is it listening: `curl -s -u USER:PASS http://127.0.0.1:8000/api/health`
