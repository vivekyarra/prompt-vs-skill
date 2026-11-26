# Official Flagsmith prompt: "set up an experiment" (Variant A, verbatim)

| Field | Value |
|---|---|
| Source URL | https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent (section "The prompt", code block titled "Prompt: set up an experiment") |
| Retrieved (UTC) | 2026-11-26T15:49:58Z |
| SHA-256 of the prompt text | `35ecba5b98c502c6aa94dccfc65ff6a9028a8672e01d02d2b07c8d1e7df7001d` |
| How hashed | UTF-8 bytes of the text between the BEGIN/END markers below, lines joined with `\n`, no trailing newline (the exact text of the page's code block, HTML-entity-decoded). Verify with `python3 prompt/verify_official_prompt.py`. |
| Edited? | No. Text below is byte-identical to the extraction. |

The page's `docs.flagsmith.com` HTML is a Docusaurus site; the prompt was extracted from the `<pre><code>` token lines of the code block, not retyped.

## Points where the prompt expects interactive human answers

Numbered per the prompt's own steps. The Phase 5 task brief must pre-answer every one of these, since headless trials have no human.

1. **Step 1, question 1 (wait for answer):** "What do you want to test?" (and the agent must find the component/file that renders it).
2. **Step 1, question 2 (wait for answer):** "What counts as success?" (conversion event goes where that happens in code).
3. **Step 1, question 3 (wait for answer):** "Which Flagsmith are we using? Flagsmith Cloud, or a local instance (API and events URL http://localhost:8000)?" For a local instance it also asks for the path to `flagsmith.env`.
4. **Step 1, offer:** "If there is no app to change, offer to build a tiny demo instead" (an offer the human may accept).
5. **Step 2 (implicit):** if the app uses no supported SDK "tell me and stop"; identifier choice is discovered from code, not asked.
6. **Step 3, Cloud:** "ask me to run `flagsmith login`" (interactive browser login; in headless trials this must be replaced by `FLAGSMITH_API_KEY`/`FLAGSMITH_ACCESS_TOKEN` in env).
7. **Step 3:** "Ask me which project and environment to use" (`flagsmith project list`, `flagsmith environment list --project <project>`), then `flagsmith init --project ... --environment ...`.
8. **Step 3 (stop condition):** if no warehouse connection exists, "send me to ...connect-a-warehouse and stop".
9. **Step 7 (approval gate):** "Plan the code changes and show them to me. Don't edit anything until I confirm."
10. **Step 8, offer:** "Offer to send test traffic with a short script that simulates a few hundred users" (human may accept or decline).
11. **Global rule:** "If something fails, stop and show me the exact error" (human-in-the-loop on every failure).

Note (observed in spike, not in the prompt): step 8 tells Python users to use `EventProcessorConfig(max_buffer_items=1)`. With flagsmith 6.7.0 this DROPS the exposure when `get_experiment_flag` is immediately followed by `track_event` (buffer of 1: oldest event evicted). See `docs/verified-facts.md`.

## Prompt text (verbatim)

~~~~text
<!-- BEGIN OFFICIAL PROMPT -->
Help me run an A/B test in this codebase with Flagsmith Experimentation. Work step by step and verify each step.
If something fails, stop and show me the exact error; don't guess or work around it.

1. Ask me these questions first and wait for my answers:
   - What do you want to test? (For example, "the copy on the checkout button".) Find the component or file that
     renders it.
   - What counts as success? (For example, "a completed purchase".) Find where that happens in the code; the
     conversion event goes there.
   - Which Flagsmith are we using? Flagsmith Cloud, or a local instance (API and events URL http://localhost:8000)?
     For a local instance, ask me for the path to the `flagsmith.env` file the local setup wrote; it holds the CLI
     credentials.
   If there is no app to change, offer to build a tiny demo instead (a single HTML page or a script) that simulates
   users, so results show up within minutes.

2. Check the stack. Read https://docs.flagsmith.com/experimentation/run-an-experiment and follow its tab for this
   app's language from here on; it has the install, initialise, exposure and conversion code for each SDK. The SDKs
   that can send events are JavaScript and React (`@flagsmith/flagsmith` 12.4.0+), Python (`flagsmith` 6.3.0+), Java
   (`com.flagsmith:flagsmith-java-client` 8.2.0+), Node.js (`@flagsmith/nodejs` 9.1.0+; the older `flagsmith-nodejs`
   package can't), Go (`flagsmith-go-client/v5` v5.3.0+) and Flutter (`flagsmith` 6.2.0+). If the app uses none of
   them, tell me and stop. Find how the app identifies users: exposures and conversions are joined per identity, so
   both must use the same identifier.

3. Connect the Flagsmith CLI. If `flagsmith --version` doesn't report v2 or later, install it with
   `curl -fsSL https://get.flagsmith.com | sh` or `brew install Flagsmith/tap/flagsmith`; use
   `npm install -g @flagsmith/cli` only as a fallback. For Cloud, ask me to run `flagsmith login`; for a local
   instance, run `source <path to flagsmith.env>`. Don't copy that file or its admin API key into this repository,
   and never print the key. Ask me which project and environment to use (`flagsmith project list`,
   `flagsmith environment list --project <project>`) and bind this repository to them with
   `flagsmith init --project <project> --environment <environment key>`. Make the API calls below with
   `flagsmith api <path>` (`--input -` reads a JSON body from stdin). Don't use the Flagsmith MCP server: it can't
   start experiments. The environment must have a warehouse: if
   `GET api/v1/environments/<environment key>/warehouse-connections/` returns none, send me to
   https://docs.flagsmith.com/experimentation/connect-a-warehouse and stop.

4. Create a multivariate flag: `flagsmith feature create <flag> --value control --enabled`, then add each variation
   with `flagsmith feature variant add <flag> --value <value> --key <key> --weight 0`. Every variation needs a key:
   one without a key records no exposures. `control` is reserved for the flag's own value, and `--variants` on
   `feature create` can't set keys. Check with `flagsmith feature get <flag> --json`.

5. Create the metric: `POST api/v1/environments/<environment key>/experiment-metrics/` with
   {"name": "<name>", "aggregation": "occurrence", "direction": "up", "definition": {"version": 1, "event": "<event>"}}
   The event name is case-sensitive and must match what the code sends.

6. Create the experiment: `POST api/v1/environments/<environment key>/experiments/` with
   {"feature": <flag id>, "name": "<name>", "hypothesis": "<hypothesis>",
   "metrics": [{"metric": <metric id>, "expected_direction": "increase"}],
   "experiment_rollout": {"enabled": true, "rollout_percentage": 100,
   "feature_state_value": {"type": "string", "value": "control"},
   "multivariate_feature_state_values": [{"multivariate_feature_option": <variation id>, "percentage_allocation": 50}]}}
   Each variation gets its `percentage_allocation` and control gets the rest. Don't start it yet: starting locks the
   flag and turns on the rollout.

7. Plan the code changes and show them to me. Don't edit anything until I confirm. Then:
   - Install or upgrade the SDK and initialise it with events enabled, using the environment key the app already
     uses for flags. For a local instance, also set the page's two self-hosted options: the API URL
     http://localhost:8000/api/v1/ and, in place of the event ingestion service URL, http://localhost:8000/api/
     (the local instance receives events itself).
   - Identify the user, then get the experiment flag (for example `getExperimentFlag`, or `useExperiment` in React)
     where the user actually sees the variation, and render by its value.
   - Track the conversion event where success happens.
   - Send buffered events before the app exits, as the page shows for this SDK.
   Keep keys out of source control, following how the app already handles configuration. Once the changes are in,
   start the experiment with `POST api/v1/environments/<environment key>/experiments/<id>/start/` and check its
   status is `running`.

8. Offer to send test traffic with a short script that simulates a few hundred users, each with its own identifier:
   get the experiment flag for each one and track the event for some of them. The SDKs send events in batches, so
   send what is left before the script exits: JavaScript `await flushEvents()`, Python
   `EventProcessorConfig(max_buffer_items=1)`, Node.js `await close()`, Java `close()`, Go `FlushEvents(ctx)`,
   Flutter `await flushEvents()`. About a minute later, call
   `POST api/v1/environments/<environment key>/experiments/<id>/results/refresh/` (allowed once every 5 minutes) and
   read `GET .../experiments/<id>/results/`. Finish with a link to the experiment:
   <dashboard>/project/<project id>/environment/<environment key>/experiments/<id>, where the dashboard is
   https://app.flagsmith.com on Cloud or http://localhost:8000 locally.
<!-- END OFFICIAL PROMPT -->
~~~~
