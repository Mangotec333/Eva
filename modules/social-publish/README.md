# EVA Social-Publish — approve-then-publish gate

Publishes content-engine drafts to **LinkedIn + X (Twitter)**, but only after
the founder **explicitly approves in Slack**. Nothing auto-publishes.

## Flow

1. A draft (text + optional image path) is submitted for approval
   (`submit_for_approval` / `POST /social/submit` / `cli.py submit`).
2. Eva posts the full draft to the founder's Slack DM (`D0ARUK4JEDA`, user
   `U0ARNV5PDRC`) with the instruction: *reply `approve` or react ✅ to publish
   to LinkedIn + X*, plus an approval link.
3. Approval is detected either by:
   - **Slack poll** — `check_slack_approvals()` looks for a ✅ reaction or an
     `approve` reply by the founder on that message; or
   - **Launcher endpoint** — `POST /social/approve/{draft_id}` (the link posted
     in Slack). This is the reliable fallback when no Slack events/socket
     receiver is running.
4. Only on approval does Eva call the existing channels connectors
   `linkedin_connector.post_to_linkedin()` and `twitter_connector.post_tweet()`.
   Results are reported back to the Slack thread.
5. A draft that is never approved is never published.

## Credentials (no secrets in code)

Read from `~/.eva/channels_config.json` (same file the channels module uses),
with env-var fallback:

| Platform | Config file keys | Env fallback |
|---|---|---|
| LinkedIn | `linkedin.access_token`, `linkedin.person_urn` | `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN` |
| X (Twitter) | `twitter.api_key`, `twitter.api_secret`, `twitter.access_token`, `twitter.access_secret` | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` (also `TWITTER_*`) |
| Slack | — | `SLACK_BOT_TOKEN` (scopes: `chat:write`, `reactions:read`, `*:history`, optional `files:write`) |

If a platform's creds are missing, the publish step **fails safe** — it posts a
clear error to Slack naming the missing env vars; it never silently skips and
never fakes a post.

> launchd does not source `~/.zshrc`. Put env vars in the plist
> `EnvironmentVariables` or restart the service from an interactive shell.

## CLI

```bash
cd modules/social-publish
python cli.py creds                                 # credential status
python cli.py submit --text "My post" --platforms linkedin,x
python cli.py list --status pending_approval
python cli.py check                                 # poll Slack, publish approved
python cli.py approve <draft_id>                    # explicit local approve+publish
python cli.py reject <draft_id>
python cli.py status <draft_id>
```

## Launcher HTTP API (:8768)

- `GET  /social/creds` — LinkedIn + X credential status.
- `POST /social/submit` — body `{text, image_path?, platforms?}` → creates draft,
  posts to Slack, returns `{draft_id, approval_link, slack, credentials}`.
- `POST /social/approve/{draft_id}` — approve + publish (the Slack link target).
- `POST /social/reject/{draft_id}` — reject.
- `GET  /social/status/{draft_id}` — draft state + publish results.
- `POST /social/check-approvals` — poll Slack for ✅/`approve` and publish.

State is stored in `social_publish.db` (gitignored) so approvals survive
restarts.
