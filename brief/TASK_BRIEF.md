# Task brief

No human is available to answer questions, so everything you need is below. Do not ask for confirmation; proceed.

## What to build

Add a Flagsmith A/B test to this app. The element under test is the text of the "Join" button.

- Control value: `Join`
- Variation value: `Join free`
- Flag name: `join_button_{{TRIAL_SUFFIX}}` (multivariate)
- Success: a visitor clicks the Join button. Conversion event name: `join_clicked`
- Identity: use the visitor identity mechanism that already exists in the app.

## Which Flagsmith

Flagsmith Cloud, sandbox project. Credentials are in these environment variables:

- `FLAGSMITH_CLIENT_KEY` - client-side environment key (for browser SDK use)
- `FLAGSMITH_SERVER_KEY` - server-side environment key (for server SDK use)
- `FLAGSMITH_API_KEY` - admin API key for the Flagsmith CLI and API (flag, metric and experiment creation)
- `FLAGSMITH_PROJECT_ID` - sandbox project id

Do not write key values into files that will be committed.

## Approval

All code changes and all Flagsmith changes in the sandbox project are pre-approved. Proceed without asking.

## Test traffic

Do not send simulated or bulk traffic to Flagsmith. It is not needed.

## Finish

When you are finished, state "DONE" followed by a one-paragraph summary of what you did.
