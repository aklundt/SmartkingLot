# SmartParkingLot - Setup Guide with Login & User Management

## What's New

✅ **Login system** - Secure authentication with Flask-Login
✅ **User management** - Create, edit, and delete users
✅ **Email support** - Associate email addresses with user accounts
✅ **Admin panel** - Manage users (admin accounts only)
✅ **Role-based access** - Admin vs regular user permissions

---

## Quick Start (Step-by-Step)

### 1. Install Dependencies

First, install the new Python packages:

```bash
pip install flask-login werkzeug
```

### 2. Add SECRET_KEY to .env

Add this line to your `.env` file:

```bash
SECRET_KEY=your-long-random-secret-key-here
```

**Important:** Use a real random string in production! You can generate one with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Replace Your Files

Copy the updated files to your backend directory:

- Replace `db.py` with the new version
- Replace `server.py` with the new version
- Replace `frontend/index.html` with the new version

### 4. Fix Port Mismatch (IMPORTANT!)

Your frontend tries to connect to port **5001**, but your Flask server runs on **5000**.

**Option A - Change Flask port:**
Add this to your `.env`:
```bash
API_PORT=5001
```

**Option B - Change frontend port:**
Edit line ~719 in `index.html`:
```javascript
return 'http://localhost:5000';  // changed from 5001
```

### 5. Create Your First Admin User

Run the setup script:

```bash
python create_admin.py
```

It will prompt you for:
- Username
- Email (optional)
- Password (hidden input)

**Alternative - Manual creation:**
```bash
python -c "import db; db.init_db(); db.create_user('admin', 'yourpassword', 'admin@example.com', is_admin=True)"
```

### 6. Restart Your Server

Stop your Flask server (Ctrl+C) and start it again:

```bash
python server.py
```

### 7. Log In!

Open your browser to `http://localhost:5001` (or 5000 depending on your config).

You should see a login screen. Use the credentials you just created.

---

## New Features Guide

### User Management (Admin Only)

After logging in as an admin:

1. Click **"Users"** in the sidebar (only visible to admins)
2. Click **"Add User"** to create a new account
3. Fill in:
   - **Username** (required)
   - **Email** (optional)
   - **Password** (required for new users)
   - **Admin privileges** checkbox (if they should be an admin)

### Editing Users

- Click **"Edit"** next to any user
- You can change:
  - Username
  - Email
  - Password (leave blank to keep current password)
  - Admin status

### Deleting Users

- Click **"Delete"** next to any user
- You **cannot delete yourself** (prevents lockout)

### Email Addresses

Emails are optional but recommended:
- Useful for password recovery (future feature)
- Helps identify users
- Can be used for notifications (future feature)

---

## API Routes Reference

### Public Routes
- `GET /health` - Health check
- `GET /` - Serve frontend
- `GET /stream` - MJPEG stream

### Auth Routes
- `POST /login` - Log in
- `POST /logout` - Log out (requires login)
- `GET /me` - Get current user info (requires login)

### User Management (Admin Only)
- `GET /api/users` - List all users
- `POST /api/users` - Create a user
- `PUT /api/users/<id>` - Update a user
- `DELETE /api/users/<id>` - Delete a user

### Parking API (Login Required)
- `POST /api/snapshot` - Submit parking detection
- `GET /api/state` - Get current parking state
- `GET /api/history` - Get historical data
- `POST /api/reset` - Reset all spots (admin only)

---

## Database Schema

### users table

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         TEXT,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT DEFAULT (datetime('now'))
)
```

---

## Security Notes

1. **Passwords are hashed** - Never stored in plain text
2. **Session cookies** - Secure, HTTP-only cookies for authentication
3. **Admin-only routes** - Protected with `@admin_required` decorator
4. **CSRF protection** - Built into Flask-Login
5. **Always use HTTPS in production** - Cookies can be stolen over HTTP

---

## Troubleshooting

### "API unreachable" error

**Cause:** Port mismatch between frontend and backend

**Fix:** See Step 4 above

### Can't log in / "Invalid credentials"

**Possible causes:**
1. User doesn't exist yet → Run `create_admin.py`
2. Wrong password → Double-check your password
3. Backend not updated → Make sure you replaced `server.py` and `db.py`

### "Users" button doesn't appear in sidebar

**Cause:** You're not logged in as an admin

**Fix:** Your user account needs `is_admin=1` in the database

### Session expires immediately

**Cause:** No SECRET_KEY set

**Fix:** Add SECRET_KEY to your `.env` file (see Step 2)

### Can't create users / Database locked

**Cause:** Database migration issue

**Fix:** The new `db.py` automatically migrates your existing database. If you see errors:
1. Backup your `parking.db` file
2. Delete it
3. Run `python -c "import db; db.init_db()"`
4. Run `create_admin.py` again

---

## Testing Checklist

- [ ] Flask server starts without errors
- [ ] Login screen appears at `http://localhost:5001`
- [ ] Can log in with admin credentials
- [ ] Dashboard loads and shows parking data
- [ ] "Users" button appears in sidebar (admin only)
- [ ] Can create a new user
- [ ] Can edit a user
- [ ] Can delete a user (not yourself)
- [ ] Can log out
- [ ] Can log back in

---

## What Changed in Each File

### db.py
- ✅ Added `users` table with email and admin support
- ✅ Added `create_user()`, `get_user_by_username()`, `get_user_by_id()`
- ✅ Added `get_all_users()`, `update_user()`, `delete_user()`
- ✅ Added `verify_password()` for secure password checking
- ✅ Auto-migrates existing databases

### server.py
- ✅ Added Flask-Login setup
- ✅ Added `User` class for session management
- ✅ Added `/login`, `/logout`, `/me` routes
- ✅ Added `/api/users` CRUD routes (admin only)
- ✅ Protected existing routes with `@login_required`
- ✅ Added `@admin_required` decorator
- ✅ `/api/reset` now requires admin privileges

### index.html
- ✅ Added login screen with styled form
- ✅ Added `credentials: 'include'` to all fetch calls
- ✅ Added 401 error handling (redirects to login)
- ✅ Added logout button in sidebar
- ✅ Added "Users" management panel (admin only)
- ✅ Added user creation/editing modal
- ✅ Automatically shows/hides admin features based on role

---

## Next Steps

Once you have login working:

1. **Create user accounts** for your team
2. **Set up HTTPS** if deploying to production
3. **Consider adding:**
   - Password reset via email
   - User activity logging
   - Two-factor authentication
   - API keys for detector.py

---

## Need Help?

If something isn't working:
1. Check the Flask server logs for errors
2. Check your browser's Developer Console (F12)
3. Verify all files were replaced
4. Make sure SECRET_KEY is set
5. Double-check the port configuration

Good luck! 🚀

---

## API Key Authentication for Detector

### Why API Keys?

The detector runs as a background service and needs to authenticate with your Flask API. API keys provide secure, session-independent authentication perfect for automated services.

### Creating Your First API Key

**Option 1 - Command Line (Easiest):**

```bash
python create_api_key.py
```

Follow the prompts to create a key, then add it to your `.env` file:

```bash
API_KEY=sk_your-generated-key-here
```

**Option 2 - Web Interface (if you're already logged in as admin):**

1. Log into the dashboard
2. Click "API Keys" in the sidebar
3. Click "Create API Key"
4. Give it a name like "Main Detector"
5. Copy the key when shown (you won't see it again!)
6. Add it to your `.env` file

### Using the API Key

The detector automatically reads `API_KEY` from your `.env` file and sends it with every request.

**In your .env file:**
```bash
API_KEY=sk_abc123...
STREAM_URL=http://localhost:8080/feed
API_URL=http://localhost:5000/api/snapshot
```

### Managing API Keys

**Via Web Interface (Admin Panel):**
- View all keys, when they were created, and last used
- Revoke keys (disables them without deleting)
- Delete keys permanently
- Create new keys with descriptions

**What You Can Track:**
- Key name and description
- Creation date
- Last used timestamp
- Active/Revoked status

### Security Best Practices

1. **Never commit API keys to git** - Keep them in `.env` only
2. **One key per detector** - Create separate keys if you have multiple detectors
3. **Rotate keys regularly** - Create new keys and revoke old ones periodically
4. **Revoke compromised keys immediately** - Better safe than sorry
5. **Use descriptive names** - "Detector #1 - Parking Lot A" is better than "key1"

### Troubleshooting API Key Issues

**Error: "API key required"**
- Make sure `API_KEY` is in your `.env` file
- Restart `detector.py` after adding the key

**Error: "Invalid API key"**
- Check that you copied the entire key (starts with `sk_`)
- Verify the key hasn't been revoked in the admin panel
- Try creating a new key

**Error: "API_KEY not found in .env file!"**
- The detector checks for `API_KEY` on startup
- Add it to your `.env` file and restart

**Key shows "Never" for Last Used:**
- The detector hasn't successfully sent any snapshots yet
- Check detector logs for connection errors

