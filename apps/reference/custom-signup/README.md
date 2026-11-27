# Fixture: custom button and event (correct)

A Node/Express app with a correct Flagsmith experiment integration and a different shape from the
standard apps: button `#signup` (control text `Sign up`, variation `Create account`), conversion event
`signup_clicked`, flag `signup_button_text`. It proves the grader is not tied to the Join / `join_clicked` task.

```
python -m grader --app-dir apps/reference/custom-signup --stack node --flag signup_button_text \
  --event signup_clicked --click-selector '#signup' --variant-values "Sign up,Create account" --out result.json
```

The self-test also grades a copy with the conversion moved to page load (must fail C3).
