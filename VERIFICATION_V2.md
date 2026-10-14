# Version 2 verification

- Backend, models, analytics, data, maps and tooling match the earlier correct project (backend includes the photo-filename field and no `data_source` column). Only the two app entry points and theme configuration were changed on top; presentation module, image, documentation and preservation tests were added. Officer app keeps the Photos grid and hides `data_source` in Related Road Work.
- Map and API call ASTs match the original contract, including map dimensions, marker data, boundary and click-to-pick arguments.
- 24 unit tests pass, including the 18 original tests and preservation / risk-comparison tests.
- Isolated citizen submission created a reference and status lookup read it back as Open. Test data was outside the delivered project; no production data was modified.
- Officer sign-in succeeded against an isolated backend. Priority map rendered; risk prediction showed 46.7% against the 39.5% baseline, with the original “Somewhat above average” category and 7.2 percentage-point difference.
- Model associations, department durability bars, annual cost chart and scaling chart rendered. Outputs remained labelled simulated or assumption-based where appropriate.
- Citizen and officer layouts checked at desktop and 390px phone width with no horizontal page overflow.
- Public Streamlit deployments are not updated or verified by this delivery. Existing login/security behavior is preserved, not audited or strengthened.
