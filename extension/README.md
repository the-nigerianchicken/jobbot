# jobbot, in the browser

Your tailored resume and your answers, on the form you are filling in.

Most applications get sent from a laptop, in a tab that knows nothing about
jobbot: the resume is in another tab, the answers are in another tab, and
marking the job applied means going back to find it. This puts all three where
the form is.

## Install it

1. Open `chrome://extensions` and turn on **Developer mode** (top right).
2. **Load unpacked**, and choose this `extension` folder.
3. Click the jobbot icon, then **Details → Extension options**, and give it your
   jobbot address and your passcode.

The passcode is traded once for the same key jobbot's own cookie carries, and
then dropped. What is stored is that key.

There is no packaged version and no Chrome Web Store listing: it reads one
person's job board, so it only makes sense unpacked.

## What it does

On an application form, jobbot appears in the bottom right.

**When it recognises the posting** — matched on the page's address, so the
apply form and the posting both count:

- **Save resume** puts the PDF jobbot wrote for this job in your downloads,
  named the way a recruiter should see it, ready for the file picker.
- **Fill what I can** writes in the fields it can match: the answers jobbot
  drafted for this job first, then your name, email, phone, school and the
  rest. It fills nothing you have already typed, skips passwords and file
  pickers, and never presses send.
- Every answer is listed. Tap one to copy it, or copy the lot.
- **I applied** moves the job to Applied, from here.

**When it does not** — a company's own careers site, or anything jobbot cannot
reach — one button hands the posting over: title, company, location and the
text of the page. It lands on your board like any other posting and you can ask
for a resume on it.

That last part is how Meta and Tesla get onto the board at all. Both careers
sites answer a browser and refuse a server, so nothing jobbot runs on a
schedule will ever see them. Reading one yourself and passing it over is the
honest way in.

## What it never does

- Submit a form. It fills what you have already read; sending it is yours.
- Type a code a site emailed you, or answer a CAPTCHA.
- Touch a password field, or store your passcode.
- Talk to anything except your own jobbot.

## Where it appears on its own

Greenhouse, Lever, Ashby, Workday, iCIMS, SmartRecruiters, Workable, Jobvite,
BambooHR, Dayforce, Oracle, SuccessFactors, Eightfold, Rippling — and the big
companies' own boards: Meta, Tesla, Apple, Google, Microsoft, Uber, Shopify,
Snap and Amazon.

Anywhere else, click the toolbar icon and it opens on that page.
