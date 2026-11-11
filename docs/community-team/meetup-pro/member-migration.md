# Temporary: Meetup Pro member migration

> This guide is for the remaining migration from Meetup Pro. It is not part of the current attendee workflow and can be removed when migration is complete.

Use the approved Meetup Pro migration invite links to invite existing members to the new Forum community. Explain that future event information and discussion will be on the Ansible Forum and registration will use Pretix.

## Distribution and tracking

1. Confirm the city and migration invite link with the Community Team.
2. Send the invite through the previously agreed Meetup Pro communication channel and explain the move to the Forum.
3. Track progress in the designated migration record, using aggregate counts where possible and avoiding unnecessary personal data.
4. Do not treat migration group membership as organiser permission. The `meetup-migrated-attendees` group is for migration tracking only.
5. See [Exporting Meetup Pro groups](exporting-groups.md) and [Exporting organisers](exporting-organisers.md) for temporary reports.

## Forum invite pilot test plan

Run this before the first Buenos Aires and London messages go to Meetup Pro members. Use a staging Forum and test links when available. Redeeming a production invite consumes one use and remains in the redemption history even after removing a test account from its groups, so get agreement before using the live links for signup tests. Never ask a real member to act as the test account.

### Pilot result

The pilot has been exercised with an existing Forum user and a new Forum account. Both received the expected group memberships, and the HTML audit updated after each redemption. Discourse prevents the same Forum account from redeeming the same link more than once. This is per account: distinct members can use the shared link until its redemption limit or expiry.

### Prepare the test

1. Choose one test email address for a new Forum account and one existing Forum account that is not staff and has not redeemed either city link. Make sure the existing account can sign in and does not already belong to either migration target group.
2. Record the test account usernames, city, test time, link description, and whether the link is a staging or production link in the migration record. Keep email addresses out of broadly shared reports.
3. Capture a baseline report and group member counts. Confirm the Buenos Aires link is configured for exactly `meetup-attendee-buenosaires` plus `meetup-migrated-attendees`; confirm London uses exactly `meetup-attendee-london` plus `meetup-migrated-attendees`. Both should show active API state, future expiry, remaining uses, and passing group/role checks.
4. Open each link in a private browser window without submitting anything. Confirm it shows the Forum invite/signup page for the expected invitation and has no expired, invalid, or unavailable message. A link that fails this step must not be distributed, even if the report says “Active (API)”.

### Test the new-account path

Run these steps for each city using the new test email. If testing on production, first confirm the team accepts the lasting test redemption in the report.

1. Start signed out in a clean browser profile. Open the matching city link and verify the invite page is the expected Forum domain.
2. Create a new account using the dedicated test email. Complete any email confirmation, approval, or password setup required by the Forum.
3. Sign in as that account. Confirm there is one account for the email and it can access the Forum.
4. Check group membership in the account's profile or the admin group member lists. It must be in its city attendee group and `meetup-migrated-attendees`; it must not be in the other city's attendee group or any `meetup-organisers-*` group.
5. Confirm the account has no staff, moderator, or administrator privileges. Confirm it can see the public Forum areas intended for attendees and does not gain access to organiser-only areas.
6. Confirm the welcome/invite experience points the member to the Forum and the normal event registration route. Record any confusing wording or missing next step.

### Test the existing-account path

Use the separate existing Forum account, signed in before opening the link. Test Buenos Aires and London with distinct test users or staging links so each result is attributable.

1. Confirm the account already exists and is not a staff account. Record its pre-test groups so the test can distinguish new access from existing access.
2. Sign in, open the matching city link, and accept the invitation if prompted. Do not create a second account or change the account's email to work around an error.
3. Confirm the same existing username remains in use and the link adds the expected city attendee and migration groups.
4. Confirm the other city's attendee group and organiser groups were not added, and that no staff or moderator permission changed.
5. Confirm the existing user can return to the Forum normally after accepting. Record whether the page clearly confirmed that the invitation was accepted.

If checking the one-redemption behavior, reopen the same link as that account after acceptance. Discourse should prevent a second redemption, and the report's unique count should not increase. Do not confuse this with a single-use link: another Forum account can still redeem it.

Also test one existing account that is already in one of the two target groups, using a staging link. Confirm accepting the link does not create a second account or duplicate group membership, and that the missing target group is added. Record the redemption as a separate event; group membership alone cannot establish which link was used.

### Verify reporting and failure handling

1. Regenerate the report after the test redemptions. For each tested link, confirm its status, expiry, redemptions/limit, remaining uses, group/role check, and unique redemption count changed as expected.
2. Confirm the city attendee and migrated group member counts each include the test user. Compare the group member lists with the report; do not infer a successful migration from invite redemption alone.
3. Check Data Explorer query 34 contains the expected test redemption under the expected city invite key. The report must attribute the invitee to the correct city link without displaying the invite key.
4. A direct link open, signup started, or email sent is not a completed migration. Treat migration as complete only after the user has a working account and the expected group memberships. If the user stops before that, record the stage reached without storing unnecessary personal details.
5. For expired or exhausted-link rejection, test only with an expired/exhausted staging link. Verify the user cannot redeem it and gets a clear next step. Do not exhaust or invalidate the production links as a test.
6. If a test user lands in the wrong group, gets duplicate-account prompts, cannot verify their email, sees an unexplained error, or receives unexpected access, pause distribution for that city. Correct the invite configuration or support instructions, then repeat the affected scenario with a clean test account.

### Close out

1. Remove test accounts from the attendee and migration groups, or retain them with an agreed test label if they are needed for monitoring. Removing them does not erase invite redemption history.
2. Save the final aggregate counts and any issues in the migration record. Do not circulate the HTML audit report outside its intended private audience.
3. After both city flows pass, send the member message in a small, monitored wave. Check the report and group memberships after the wave, then expand distribution if no failures appear.

There is no invite-link click count in the current report. Discourse exposes successful redemptions and current group membership, but not how many recipients opened the link or abandoned signup. For the pilot, record message delivery/recipient totals separately from Forum redemption totals; the gap is a useful signal but does not identify the exact point of abandonment.

| Migration stage | Evidence to record | What a gap can tell you |
| --- | --- | --- |
| Message sent | Recipients and delivery/bounce totals from the Meetup Pro channel | Delivery problem or stale contact data |
| Link opened | Not available in the current report | Cannot distinguish unopened messages from people who opened and left |
| Invite redeemed | Query 34 and the per-link redemption total | The user accepted the invite; this alone does not prove the account is active or in the right groups |
| Account usable | Test account can sign in and access the Forum | Activation, approval, password, or account-matching issue |
| Correct groups | Membership in the city attendee and migration groups; absent from other-city and organiser groups | Invite configuration or redemption processing issue |
| Ongoing participation | Later RSVP or event participation, if tracked through the normal event process | Whether migration led to continued engagement |

Do not report a “click-through rate” from redemptions divided by messages delivered: that ratio combines unopened links, signup abandonment, and account/group failures. Report the delivered count, redeemed count, and verified group-member count as separate funnel stages.
