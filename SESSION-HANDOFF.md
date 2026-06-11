# EHS Hub / AIM website — Session Handoff

Canonical handoff for the EHS Compliance Hub (hub.aim-env.com) and the aim-env.com WordPress site. Read this first on a new session. Real source of truth = git history (this repo; Vercel auto-deploys main) + the Supabase project. This doc summarizes current state for a cold resume.

## Current state — 2026-06-11
- Hub repo HEAD: main @ 6f61f677 (live on hub.aim-env.com via Vercel).
- Hub source: single file index.html at repo root (all HTML/CSS/JS inline).
- Supabase project ref: xnaseutcmkgukphslpkv. Admin = chad@aim-env.com (is_admin() checks the JWT email).
- aim-env.com: WordPress, edited via the WPVibe MCP. Currently BLOCKED (see open items).
- QuickScope is a SEPARATE project (its own repo and its own wrap). NOT covered by this handoff.

## Session 2026-06-11 — Hub fixes #14/#15/#16, Rule-lookup scroll, Admin Members directory (#12)
Commits (all verified live on hub.aim-env.com):
- 8ab6066a — #14 ADI heading renamed to Applicability Determination Index (ADI) and the tab now reads ADI; #15 auto-scroll packet and ADI results into view; #16 Community tab unread badge.
- 2e790f92 — #15 extended so Rule-lookup results (the #rA container) also auto-scroll.
- 6f61f677 — #12 Admin Members directory.

Hub UI changes (index.html; all additions are appended self-contained script/style blocks, existing code untouched):
- #14: ADI screen heading and tab de-duplicated. One remaining ADI Index phrase is inside the sign-in gate sentence and was left on purpose.
- #15: a MutationObserver on #pA, #adiA, and #rA smooth-scrolls a result into view when it populates and is below the fold. Matches the app existing rule-lookup scroll pattern.
- #16: the Community (ask) tab shows a red unread count of approved community_posts newer than the member last visit (localStorage key hubAskSeen); it clears when the tab is opened.
- #12 Members: a new Members card at the top of the Admin console (section id p-admin). Lists every member with name, email, company, photo or initials, verified-expert status, bio, state and facility type, join date, last-active, last sign-in, and post/reply counts. Search plus sort. Per-member actions: Edit profile fields; promote or demote verified-expert (the blue check); Deactivate or Reactivate (reversible soft-delete); Message (a hook for Build 2 that currently shows a coming-next toast). Admin-only and server-enforced.

Supabase migration applied this session: members_admin_build1 (version 20260611143910):
- Added column profiles.deactivated_at (reversible soft-delete).
- Updated is_approved() so deactivated members lose member-tool access; admin is always exempt.
- Added admin_list_members(): an is_admin()-gated SECURITY DEFINER RPC returning rich member data (profiles + auth.users + activity counts). Verified: admin gets data, non-admin gets a not-authorized error.
- Member writes go through sbc.from(profiles).update() directly. The profiles_admin_all RLS policy plus the profiles_guard and protect_approved triggers already pass through for admin.

Tickets resolved this session (replies posted): #14, #15, #16, #12. Ticket #18 was replied to but left OPEN because it is blocked.

## Open / next up
- Build 2 — Private messaging: DESIGNED, NOT BUILT. One-to-one DMs (threads and messages) with RLS so only the two participants plus admin can read a thread; an inbox UI with an unread badge and compose/reply; an admin Message entry from the Members tab; plus block-a-user and report-a-message with admin review. AWAITING CHAD DECISION on member-to-member openness: (A) any member to any member [the original spec]; (B) members can message verified-experts and admin only, while experts and admin can message anyone [recommended for the public beta, because signups are auto-approved, so option A effectively lets anyone who signs up DM anyone]; (C) admin-initiated only. Build on his pick. The openness gate will live in one RPC so it is easy to change later.
- #18 — QuickScope ad on aim-env.com: BLOCKED. WPVibe cannot reach the site; every call (REST, WP-CLI, site_info) returns the SiteGround bot challenge (sgcaptcha, HTTP 202). Fix: allowlist WPVibe in SiteGround security (Site Tools) or reconnect the site, then update the QuickScope ad to add the El Paso module and the line more modules coming soon. The current ad copy was captured and the change is ready to apply once access is restored.
- New tickets that arrived and are still UNHANDLED: #19 (add state regs and other-facility consulting), #20 (add another nav item inside the admin tab), #21 (ability to delete members; relates to the Members tab; note the current Deactivate action is a reversible soft-delete, not a hard delete). Pre-existing open and Chad-flagged: #11, #13, #17. Also #10 is resolved but has no posted reply.

## Key facts and gotchas for resuming
- Editing the Hub: index.html is edited through the GitHub web editor in Chrome (CodeMirror 6). Reliable content replace: focus the .cm-content element, dispatch a synthetic Ctrl+A KeyboardEvent (the plain key chord does NOT trigger CodeMirror select-all), then call document.execCommand with insertText and the full file content, then commit. There is NO local repo copy on this machine; always fetch the CURRENT file via the GitHub contents API (api.github.com, public repo, CORS-open) and edit against the live file so earlier work is never overwritten.
- Content filter: returning raw index.html or app source through the Chrome tools is blocked because the file embeds config. Work on the source inside the page and return only counts or booleans; read content via the GitHub API and atob.
- Reusable app globals: sbc (the supabase-js client, which carries the signed-in user JWT), isAdminUser(), esc(), timeAgo(), avatarHTML(), toast(), selectTab(), buildAdminTab(), loadAdmin(), goTab(); plus the SB, KEY, HDRS, and FN constants.
- Admin model: is_admin() is true when the lowercased JWT email equals chad@aim-env.com. The profiles_admin_all RLS policy gives admin full read and write on profiles; the profiles_guard and protect_approved triggers pass through for admin.
- WPVibe and SiteGround: the bot challenge currently blocks all WPVibe access to aim-env.com. Surface this rather than retrying.

