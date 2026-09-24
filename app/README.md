# jobbot on your phone

One Cloudflare Worker (free tier) and one D1 database. This is the whole system
as you see it: new postings, the resume built for each, the prepared answers,
one tap to apply, and every application you have ever sent - editable, with
outcomes. There is no digest to read and no spreadsheet to keep in step.

## What the two tabs are

**Jobs** - the queue, most urgent first.

- **Needs you** - the apply run stopped at something only a person can do (an
  emailed code, a CAPTCHA), or the resume could not be built.
- **New postings** - found, and nothing has been written for them. **Apply for
  me** writes a resume tailored to that posting and then applies where jobbot
  can submit (Greenhouse, Lever, Ashby); **Just write the resume** stops after
  writing it. On any other site the button is **Write my resume** and you send
  it yourself.
- **Ready to apply** - resume built and waiting on you.
- **Applying** - a run is filling the form; **Stop** cancels it.
- **Writing resumes** - a resume you asked for is being written.
- **Applied recently** - the last week only. The rest lives in the other tab.

Nothing is written until you ask: **Select** in the header turns on checkboxes
so a pile of look-alike postings can be archived in one tap, and archived jobs
stay reachable under **Show archived** with **Put it back**. The switch lives in
`criteria.yaml` as `resumes.on_request` if you ever want a resume for every
match again.

**Applications** - the tracker. Search, filter by outcome, tap any row to change
the outcome, date, referral or notes, **+** to add one by hand, **Export** for a
CSV with the same columns the old spreadsheet had.

## Why it looks like this

It is a list. He opens it twenty times a day between classes to answer one
question - is this worth my resume - so the design is whatever gets out of the
way: the phone's own typeface, black on white, one red for the thing that
undoes. The work went into behaviour instead. One obvious action per screen,
swipe a job left to archive it, and undo in the toast rather than "are you
sure" in a dialog. The page lives in `page.js`; `worker.js` is the server.

## Telling Claude what to change

Every job has a box: *Lead with the GPU work. Drop the Helix Labs bullet. Say ETL,
not pipeline.* It is saved with the job, and **Write it again with this** sends
it along with the request. jobbot puts it at the top of the JD.md that the
model reads, under a heading saying it came from you, with one instruction:
follow it unless it would mean claiming something you have not done.

## How state moves

```
GitHub Actions  --(/api/ingest)-->  D1  <--(taps)--  the app
       ^                                  |
       +--------(/api/events)-------------+
```

Every workflow ends with `python -m jobbot.appsync sync`: it sends the current
jobs to the app and picks up whatever you tapped while your laptop was off. A
tap you make is never undone by a run that started before it.

## Deploy or redeploy

```bash
cd app
npx wrangler deploy
```

First time only:

```bash
npx wrangler d1 create jobbot                       # id goes in wrangler.toml
npx wrangler d1 execute jobbot --remote --file=schema.sql
npx wrangler secret put GH_TOKEN        # fine-grained PAT: Contents read/write, Issues write
npx wrangler secret put APP_PASSCODE    # what you type to open the app
npx wrangler secret put INGEST_TOKEN    # same value as the APP_TOKEN repo secret
```

and two repository secrets, so Actions can reach the app:
`APP_URL` (the workers.dev URL) and `APP_TOKEN` (the INGEST_TOKEN value).

To load your history and the jobs jobbot already knows about:

```bash
python -m jobbot.seed_store                          # writes app/seed.sql
cd app && npx wrangler d1 execute jobbot --remote --file=seed.sql
```

It is safe to run twice: jobs are replaced by id, and an application is only
added if nothing with the same company, role and date is there already.

## Changing it

```bash
node app/test_worker.mjs     # 57 offline checks: auth, feed, buttons, tracker
node app/preview.mjs         # the real app on http://localhost:8787, passcode: preview
```

`preview.mjs` runs the actual worker against the real schema in memory and the
repo's own resumes, so what you see locally is what deploys.

## Notes

- The passcode is the only lock, so keep the URL private. The GitHub token can
  read this repo and write its issues; the ingest token can only report jobs in.
- Free tier: 100,000 requests a day, and 5 GB of D1. This uses a rounding error
  of both.
