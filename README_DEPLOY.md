# QuantEngine — public deployment

This project is prepared for Render. It is not public until you connect it to a Git repository and deploy it from your own Render account.

## Easy deployment (phone or laptop)
1. Sign in to GitHub and create a **private or public** repository named `quantengine-dashboard`.
2. Upload all files in this folder to the repository (not the ZIP file itself).
3. Sign in to Render and choose **New + → Blueprint** (or create a Web Service).
4. Connect the GitHub repository. Render will read `render.yaml`, install `requirements.txt`, and start the app.
5. When deployment succeeds, Render gives you a public `https://...onrender.com` address. Open that address on your phone.

If creating a Web Service manually, use:
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn server:app`

## Important
- This starter is for research/demo use, not financial advice or live order execution.
- The dashboard's strategy stats/equity curve are sample/demo values. Verify CoinDCX endpoint compatibility and scan output before relying on it.
- Never upload exchange API keys or passwords to a public repository.


## Private Admin Login (required before public launch)
- Admin page: append `/admin` to your deployed website address. The public homepage does not show the admin identity or an admin link.
- Username defaults to `krishkumar`; you can override it with the `ADMIN_USERNAME` environment variable.
- In Render → your service → **Environment**, add these variables:
  - `ADMIN_USERNAME` = `krishkumar`
  - `ADMIN_PASSWORD` = choose a strong, unique password (do not put it in GitHub or send it in chat)
  - `SECRET_KEY` = a long random secret, at least 32 random characters
- Do not deploy publicly until both `ADMIN_PASSWORD` and `SECRET_KEY` are set. Admin login intentionally stays disabled otherwise.
- Admin can post a public announcement and turn the scanner / Strategy Lab sections on or off. It does not place trades or control exchange accounts.
- Render free instances have temporary local storage; saved site settings may reset after restart/redeploy. For reliable persistence, add a persistent disk or database on a plan that supports it.
- Admin username/password are environment variables, not hard-coded in this ZIP. Keep the repository private if you prefer, and never commit secrets.
