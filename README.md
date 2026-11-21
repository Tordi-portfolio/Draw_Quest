# DrawQuest

A creative task platform: the admin publishes drawing tasks with a $ reward, users draw and upload, the admin approves or rejects, and approved rewards are credited to the user's dashboard.

Built with Django 5, SQLite, and a hand-written "2027" dark-glass UI (no front-end build step).

## Run it

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser  # this account is your admin
python manage.py seed_demo        # optional: 6 sample tasks + welcome post
python manage.py runserver
```

Open http://127.0.0.1:8000

## How it works

**Users** (sign up at `/signup/`)
- `/tasks/` task board, filter by category, search
- Task page: read the brief, drag-and-drop upload your drawing, submit
- `/dashboard/` points balance, lifetime earnings, submission counts, activity ledger, admin announcements
- `/submissions/` every drawing with its status and the admin's feedback

**Admin panel** (`/panel/`, staff only, i.e. your superuser)
- Overview: queue size, users, total paid
- Review queue: open a drawing, **Approve & pay** (credits the user instantly, once) or **Reject** (feedback required)
- Tasks: create, edit, hide/publish; each task has a reward in $
- Users & dashboards: see any user's balance and ledger, and credit or deduct points with a note
- Announcements: post news (optional image) to every user's dashboard

The Django database admin is at `/admin/` (superuser/staff login).

## Deposits (USDT on BSC)

1. **Set your receiving wallet in the backend.** Log in at http://127.0.0.1:8000/admin/ with your superuser, open **Deposit wallet**, paste your BSC address (`0x` + 40 characters) and save. It appears on the deposit page immediately. Only superusers can see or change it, the format is validated, and the admin's **History** button records who changed it and when. (If none is saved there, the `DRAWQUEST_USDT_WALLET` environment variable / `DEPOSIT_WALLET_ADDRESS` in `settings.py` is used as a fallback.) Until a valid address exists, users see "deposits unavailable" instead of a wrong address.
2. Users open `/deposit/`, see network **BSC** (BNB Smart Chain, BEP-20), token **USDT**, and your wallet address with a copy button and loss-of-funds warnings.
3. After sending, they submit the amount and the **transaction ID (TxID)**. Each TxID can only be submitted once.
4. You verify it at `/panel/deposits/` (there's an "Open on BscScan" link and a checklist), then **Verify & credit** the amount you saw on-chain (or reject with a note). Credits are written to the user's ledger.

DrawQuest doesn't watch the blockchain automatically; deposits are verified by an admin. Automatic detection would need a BSC node or API service.

## Updating a user's balance manually

Admin panel → **Users & dashboards** → **Edit balance**. Enter a positive amount to add or a negative amount to deduct, plus a note. It's logged in the user's ledger and can't take a balance below $0.

## Withdrawals

- Users request a payout at `/withdraw/` once their balance reaches **$500** (change it with the env var `DRAWQUEST_MIN_WITHDRAWAL`, or `WITHDRAWAL_MIN` in `settings.py`).
- They choose a method (bank transfer, PayPal, mobile money, crypto) and enter payout details. One request can be open at a time.
- On request, the amount is **taken off their balance immediately** and held, so it can't be spent twice.
- Admins review requests at `/panel/withdrawals/`. You send the money yourself, then either:
  - **Mark as paid**: requires a payment reference (transfer ID / transaction hash) as proof, or
  - **Reject & refund**: requires a note; the held amount returns to the user's balance.
- Every step is recorded in the user's ledger, and users see their withdrawal history and your notes.
- DrawQuest does not move money itself; payouts are sent manually by the admin. Automating them needs a payment provider.

## Notes

- A user can't resubmit to a task while a submission is pending or approved; after a rejection they can try again.
- The reward is snapshotted when a user submits, so editing a task's price later doesn't change pending work.
- Every balance change writes a `PointTransaction` row, so balances are always auditable. Balance is read-only in the Django admin on purpose.
- To make someone else an admin: in `/admin/` tick **Staff status** on their user.

## Before going live

- Set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Run `python manage.py collectstatic` and serve `staticfiles/` and `media/` from your web server or object storage.
- Switch to PostgreSQL for real traffic.
- Withdrawals are reviewed and paid manually. Decide how you'll verify user identity, handle fees and taxes, and comply with payout regulations in the countries you serve before paying real money.
- Payout details (bank/wallet info) are stored as plain text in the database. Restrict admin access and use an encrypted database/backups in production.
"# Draw_Quest" 
