# Suite 38.A4 — Rolling over passwordless accounts

## Background

Before suite 38 (38.A1/38.A2 removed the passwordless "lazy-auth" sign-in),
a user could get a `neon_auth.user` row with no password at all — sign-in
was just "enter your email." `theCommonsWeb/src/app/(portal)/signin/SignInForm.tsx`
now requires email **and** password (confirmed by reading the file — there is
no passwordless code path left). Anyone whose account never got a
credential-provider password is now locked out: there is no password for
them to type.

**Decision (2026-07-31): send each affected user a password-reset email.**

**How we got here (for context on why there's no shortcut).** The working
tree at the time of this writing has an in-progress, not-yet-committed diff
removing the passwordless flow entirely: `theCommonsWeb/src/lib/lazy-auth-plugin.ts`
(the `/enter` endpoint that logged a user in by email alone and set a
session cookie) is deleted, along with the old
`theCommonsWeb/src/app/(portal)/set-password/*` page and
`theCommonsWeb/src/app/api/auth/set-password/route.ts`. That old
`/set-password` page was the previous self-serve fix for exactly this
problem — but it only worked because a passwordless user already had a
valid session (from `/enter`) and could add a password to it. With
`lazy-auth-plugin.ts` gone, there is no way left to get a session without a
password, so that door is closed too. This is why a token-based,
no-session-required reset link (Better Auth's `sendResetPassword` flow) is
the only remaining path — it's the one mechanism that doesn't require the
user to already be signed in.

## Status: blocked on frontend/auth wiring — do not `--send` yet

This doc and the management command it describes are **prepared, not run**.
Before any real send, the reset link the email points to must actually work.
As of this writing it does not. Read "Prerequisite wiring" below before doing
anything else with this runbook.

## 1. Identify affected users

Affected = a `neon_auth.user` row with **no** `neon_auth.account` row where
`providerId = 'credential'` AND `password IS NOT NULL`.

Dry run (identifies and prints only — sends nothing):

```bash
cd backendServer
DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py rollover_passwordless_accounts
# or against a real DB:
DJANGO_SETTINGS_MODULE=backend.settings.prod uv run python manage.py rollover_passwordless_accounts
```

This is implemented in
`backendServer/events/management/commands/rollover_passwordless_accounts.py`.

**Why raw SQL, not the ORM.** `events/models.py` declares
`BetterAuthAccount.user_id` as a Django `TextField`, but the live
`neon_auth.account."userId"` column is actually `uuid` — confirmed by
querying `information_schema.columns` against the test DB:

```
('neon_auth', 'account', 'userId', 'uuid')
('neon_auth', 'user', 'id', 'uuid')
```

An ORM anti-join (`BetterAuthUser.objects.exclude(id__in=BetterAuthAccount.objects.filter(...).values("user_id"))`)
binds the subquery's `userId` values as text (per the model's field type)
against `u.id` (uuid); Postgres has no `uuid = text` operator for that shape
and raises `operator does not exist: uuid = text` — reproduced while
building this command, before the fix. The command instead runs a plain
raw-SQL `LEFT JOIN ... WHERE a.id IS NULL` anti-join with no cast, since both
columns really are `uuid`. **This is a real model/schema drift** worth a
follow-up: `BetterAuthAccount.user_id` should probably be declared to match
the actual `uuid` column type (though since `managed = False`, nothing
enforces it and ORM reads still work — Python just gets the UUID's string
form back — the drift only bites when you build a cross-model join, as here).
Neither mirror model is migrated by Django in any case (`managed = False`
on all `neon_auth` mirrors — never run `makemigrations`/`migrate` against
them).

Verified working: a dry run against the shared test DB found 2 real
leftover accounts matching the pattern (`diag4+…@example.com`,
`s37e2e-drive1@example.com`), and `--help` / `--limit` both work as expected.

## 2. Prerequisite wiring — blocking, must land before `--send`

The ticket's fallback plan was "email users a link to the existing
`/forgot-password` page where they self-serve." **Investigation shows this
does not currently work, for two independent reasons:**

### 2a. Better Auth's native reset-password endpoint is disabled

`theCommonsWeb/src/lib/auth.ts` configures:

```ts
emailAndPassword: { enabled: true, autoSignIn: true },
```

No `sendResetPassword` callback. Better Auth's own source
(`better-auth/dist/api/routes/password.mjs`, `/request-password-reset`
endpoint) checks this explicitly, **before** creating any reset token:

```js
if (!ctx.context.options.emailAndPassword?.sendResetPassword) {
    ctx.context.logger.error("Reset password isn't enabled...");
    throw APIError.from("BAD_REQUEST", { code: "RESET_PASSWORD_DISABLED" });
}
```

So calling `authClient.requestPasswordReset({ email })` today returns a 400
`RESET_PASSWORD_DISABLED` — it doesn't even generate a token, regardless of
what frontend page calls it.

**Fix required:** add an `emailAndPassword.sendResetPassword` function to
`auth.ts` that sends the email Better Auth generates the token/url for (via
Brevo, or whatever transactional path the Next side uses). This also implies
adding `resetPasswordTokenExpiresIn` if the default 1-hour window isn't
wanted.

### 2b. There is no frontend page to consume a reset token, and `/forgot-password` is a stale stub

- No `/reset-password` or `/reset-password/[token]` page exists anywhere
  under `theCommonsWeb/src/app` (searched — zero matches). Better Auth's
  `/reset-password/:token` callback redirects to a `callbackURL` you supply
  as `redirectTo`; there is currently nothing at that URL to receive the
  token and call `authClient.resetPassword({ token, newPassword })`.
- The existing `/forgot-password` page
  (`theCommonsWeb/src/app/(portal)/forgot-password/ForgotPasswordForm.tsx`)
  is **not** a working self-serve reset flow. It's a static informational
  stub left over from the passwordless era. Its copy literally says:

  > "The Commons doesn't send password reset emails. In most cases you don't
  > need one — just enter your email on the Sign In page and continue
  > without a password."

  That's now false (passwordless sign-in is gone), and the form's
  `handleSubmit` just flips a `submitted` boolean to show a canned message —
  it never calls any Better Auth API (`authClient.requestPasswordReset` or
  anything else). Linking rolled-over users here today would land them on a
  page that tells them to do something that no longer works.

**Fix required:**
- Rewrite `ForgotPasswordForm.tsx` to actually call
  `authClient.requestPasswordReset({ email, redirectTo: '/reset-password' })`
  and show a real "check your email" state.
- Add a `/reset-password/[token]` (or matching `redirectTo`) page that reads
  the token and calls `authClient.resetPassword({ token, newPassword })`.

**None of the above is in scope for 38.A4** (scope was: management command +
this doc, no edits to `auth.ts` or frontend routes). It is called out here
as the blocking prerequisite. Track it as a follow-up ticket before running
`--send` for real.

## 3. How the batch send works (once 2a/2b are wired and verified)

```bash
cd backendServer

# Dry run — always do this first, re-check the printed email list
DJANGO_SETTINGS_MODULE=backend.settings.prod uv run python manage.py rollover_passwordless_accounts

# Canary: send to just the first affected account, confirm it lands and the
# link works end-to-end (see step 5) before doing everyone
DJANGO_SETTINGS_MODULE=backend.settings.prod uv run python manage.py rollover_passwordless_accounts --send --limit 1

# Full send
DJANGO_SETTINGS_MODULE=backend.settings.prod uv run python manage.py rollover_passwordless_accounts --send
```

The command sends via `events.email_service.send_email` (Brevo
transactional email — same primitive the digest emails use). It is
idempotent to re-run: if a user sets a password after being emailed, they
will have a `neon_auth.account` row with `providerId='credential'` and a
non-null password and will no longer show up in the affected-user query, so
re-running the dry run naturally shrinks the list and re-sends will not
re-email people who already rolled over.

## 4. Email copy

Subject: `Action needed: set a password for your Commons account`

Body:

> Hi {name},
>
> We've changed how sign-in works on The Commons. Your account was created
> before we required a password, so the old "just enter your email" sign-in
> no longer works for you.
>
> [Set your password]({SITE_URL}/forgot-password) — it only takes a minute.
>
> If you don't recognize this account, you can safely ignore this email.
>
> — The Commons

`SITE_URL` defaults to `https://www.thecommons.town` (same env var and
default `email_service.py` already uses for the newsletter manage link).
The link target (`/forgot-password`) is the page named in section 2b — do
not send until that page actually drives a working reset, or update this
copy/command to point at wherever the fixed flow lives.

## 5. Verifying a user can sign in afterward

Once 2a/2b are wired:

1. Pick one affected email from the dry-run list (or use the `--limit 1`
   canary send).
2. Confirm the email arrives (Brevo dashboard or the inbox) and the link
   works: clicking it should reach a real "set your password" form, not the
   stale copy described in 2b.
3. Submit a new password there.
4. Confirm a `neon_auth.account` row now exists for that user with
   `providerId='credential'` and a non-null `password`:
   ```sql
   SELECT a.* FROM neon_auth."account" a
   JOIN neon_auth."user" u ON u.id = a."userId"
   WHERE u.email = '<the test email>' AND a."providerId" = 'credential';
   ```
5. Go to `/signin`, enter that email + the new password, confirm sign-in
   succeeds and redirects normally (`SignInForm.tsx`'s `login()` /
   `resolveRedirect` path).
6. Re-run the dry-run command — that user should have dropped out of the
   affected list.

## Repo stance reminders

- `neon_auth` mirror models (`BetterAuthUser`, `BetterAuthAccount`, etc. in
  `backendServer/events/models.py`) are `managed = False`. Never run
  `makemigrations`/`migrate` against them; this command only reads
  (`SELECT`, no writes) from that schema.
- No email verification for MVP — this rollover doesn't add any; it's
  strictly about restoring the ability to sign in with a password.
