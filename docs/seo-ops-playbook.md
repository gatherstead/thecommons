# SEO Ops Playbook — Out-of-Codebase Steps

Manual and account-level SEO work for The Commons. Nothing here requires a code
deploy — but several steps unblock in-codebase tickets (notably T5, the GSC
verification code).

Work through these in order. Steps that are blocked until a code ticket lands are
marked **[needs T<n>]**.

---

## 1. Google Search Console — verify and submit sitemap

**[needs T1 + T3 deployed to prod]**

### Verify the domain

1. Go to [search.google.com/search-console](https://search.google.com/search-console)
   and sign in with the Google account that will own The Commons property.
2. Click **Add property → URL prefix** and enter `https://thecommons.town`.
   (URL-prefix, not Domain — the domain method requires DNS TXT access which may
   be harder to confirm.)
3. Choose **HTML tag** verification. Google shows a `<meta name="google-site-verification"
   content="...">` tag. Copy the content value (looks like `abc123XYZ`).
4. In `theCommonsWeb/src/app/layout.tsx`, add to the root `metadata` export:
   ```ts
   verification: { google: 'PASTE_CODE_HERE' },
   ```
   Deploy this change to production.
5. Return to GSC and click **Verify**. GSC fetches the live page, finds the meta tag,
   and marks the property as verified.

### Submit the sitemap

6. In the left sidebar, go to **Sitemaps**.
7. Enter `https://thecommons.town/sitemap.xml` and click **Submit**.
8. GSC will show "Success" within a few minutes once it can fetch the file.
9. Check back in 24–48 hours — GSC will report how many URLs it discovered and
   whether any have errors.

### What to watch (first 4 weeks)

- **Coverage report:** Should show event pages moving from "Discovered — currently
  not indexed" → "Indexed." If pages stay in "Crawled — currently not indexed,"
  it usually means thin content or low PageRank; hub pages (see `seo-hub-pages.md`)
  help here.
- **Enhancements → Events:** Appears once the JSON-LD from T2 is deployed. Should
  show "Valid" for event pages. "Errors" here mean the LD+JSON has a required field
  missing — fix per the error description.
- **Core Web Vitals:** Won't populate until GSC has real CrUX data (takes ~28 days
  of traffic). Revisit after a month.

### Monthly check (recurring)

Use this prompt with Claude or run manually:
> "I'm reviewing Google Search Console for thecommons.town. Summarize: (1) total
> indexed URLs vs. sitemap submitted, (2) any new manual actions or security issues,
> (3) top 10 queries by impressions this month vs. last month, (4) any Event
> enhancement errors. Flag anything that needs action."

---

## 2. Google Business Profile

### Why

GBP listings appear in the "local pack" — the map + 3-business block that shows up
for queries like "events near me" or "things to do in Chapel Hill." Without a GBP,
The Commons doesn't appear there at all.

### Setup steps

1. Go to [business.google.com](https://business.google.com) and sign in.
2. Click **Add your business** and search for "The Commons" — if it doesn't exist,
   create it.
3. Business name: **The Commons**
4. Category: search for **"Community Organization"** (primary). Add secondary:
   **"Event Planning Service"** if available.
5. Service area: select **Chapel Hill, NC** and **Carrboro, NC** (and Pittsboro if
   covered). Do *not* enter a street address if there's no physical storefront —
   use the service-area-only option.
6. Website: `https://thecommons.town`
7. Phone: use a consistent number (or leave blank if none) — whatever you list here
   is the canonical NAP phone.
8. Verify the listing. Google will offer a video call or postcard. Postcard takes
   5–7 days; video call is faster.
9. Once verified, complete the profile: add a description (use the About page copy),
   upload a logo/cover photo, set business hours if applicable.

### Weekly posting (recurring)

GBP Posts drive engagement signals. Post 1–2 event highlights per week:
- Go to **Posts → Add update**
- Title: event name
- Body: 1–2 sentences, date/time/location
- Button: "Learn more" → link to `https://thecommons.town/events/<uuid>`

Use this Claude prompt to draft a week's worth of GBP posts:
> "Write 2 Google Business Profile posts for The Commons, a community events
> aggregator in Chapel Hill/Carrboro, NC. Each post should be 2–3 sentences,
> highlight a specific upcoming event, include the date and venue, and end with
> a call to action linking to the event page. Events: [paste event titles, dates,
> venues]. Keep the tone warm and local — not promotional."

---

## 3. NAP consistency audit

NAP = Name, Address, Phone. Google uses NAP consistency across the web as a local
trust signal. Inconsistency (different business names, conflicting addresses) hurts
local rankings.

### Canonical NAP for The Commons

| Field | Value |
|-------|-------|
| Name | The Commons |
| Service area | Chapel Hill / Carrboro, NC |
| Website | https://thecommons.town |
| Email | (use whatever is on the About page) |
| Phone | (if none, leave blank everywhere — don't list a number on some listings and not others) |

### In-codebase: verify consistency

Check that these three places agree with the canonical NAP above:
- `theCommonsWeb/src/components/layout/Footer.tsx` — copyright bar currently reads
  "Chapel Hill Area, N.C." ✓
- `theCommonsWeb/src/app/about/page.tsx` — reads "Chapel Hill Area, N.C." ✓
- If you add GBP, make sure GBP business name = "The Commons" (not "The Commons NC"
  or "thecommons.town")

### Out-of-codebase: directory listings

Submit The Commons to these local directories with the exact canonical NAP:

1. **Yelp for Business** — [biz.yelp.com](https://biz.yelp.com). Category: "Community Service/Non-Profit."
2. **Nextdoor** — claim/create a business page at [business.nextdoor.com](https://business.nextdoor.com).
3. **Chapelboro.com** — email the editorial team; ask for a community resource link.
4. **WCHL 97.9 / Chapelboro** — same as above; they list local event resources.
5. **Town of Carrboro website** — contact the town's community events coordinator and
   ask to be added to their community resources page.
6. **Town of Chapel Hill website** — same.

Use this Claude prompt to draft outreach emails:
> "Write a short outreach email (under 150 words) to the editor of [Chapelboro /
> WCHL / Town of Carrboro website]. We're asking them to include a link to
> thecommons.town on their community resources page. The Commons is a free,
> community-run events aggregator for Chapel Hill and Carrboro — no ads, no
> algorithm, just a clean list of what's happening locally. Tone: neighborly,
> not promotional. Sign it from [your name], The Commons."

---

## 4. Review ask flow

Google reviews on the GBP listing are a ranking signal for the local pack.

Once GBP is verified and the weekly digest email is running (via Brevo), add a
single line to the digest footer:
> "Find us helpful? [Leave a quick review on Google →](GBP_REVIEW_LINK)"

The GBP review link looks like:
`https://search.google.com/local/writereview?placeid=YOUR_PLACE_ID`

Find your Place ID:
1. Search for "The Commons" on Google Maps after the GBP is live
2. Click the listing, look at the URL — `placeid=ChIJ...` is your ID
3. Construct the direct review link and paste it into the digest template
   (`backendServer/templates/` — whichever template Brevo uses for the weekly digest)

---

## Status tracker

| Step | Owner | Status | Notes |
|------|-------|--------|-------|
| GSC verify | — | not started | needs T1+T3 deployed |
| GSC sitemap submit | — | not started | needs GSC verified |
| GBP create + verify | — | not started | postcard takes 5–7 days |
| NAP audit (in-codebase) | — | not started | quick check |
| NAP audit (Yelp, Nextdoor) | — | not started | |
| Local outreach (Chapelboro, towns) | — | not started | |
| Review link in digest | — | not started | needs GBP Place ID |
