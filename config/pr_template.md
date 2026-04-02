### JIRA Story
Link : https://wenergysoftware.atlassian.net/browse/{{TICKET}}
Target Branch: {{TARGET_BRANCH}}
___
##### How to update checkboxes below: 
###### Create the PR and then select checkboxes[honestly]!!! 
or 
###### Add a `x` in the square brackets for completed items
___
### Type of Change
- [x] Bug Fix
- [ ] Feature
- [ ] Refactor
___
#### Testing environment(dev/project box) - 

### Universal Checklist (Mandatory for all PRs)

- [x] All commits have `JIRA ID` prefixed of the parent ticket (not sub-task)
- [x] Fix versions updated on JIRA ticket
- [x] PRs created for all required release branches (incl. `develop-mt`/`develop-u`)
- Config changes, if any:
  - [ ] Updated on Parent ticket (`Release Info` → `Config Change`)
  - [ ] Default setting added to `settings.yml`
  - [ ] No hardcoded secrets or tokens introduced
- [ ] Extra debug logs / console statements added:
   - Reason: 
- Self review checks for: 
  - [x] Readability 
  - [x] Maintainability
  - [x] Coding standards
  - [x] Linting rules
- [ ] DB Migrations have failsafes (should not fail, if re-run)
- [x] Dev testing notes/screenshots added to ticket
___
### Bug Fix Checklist (Required for Bug fixes)
- [x] RCA clearly identified & updated on JIRA
- [x] Tested the complete user flow for this feature, not just the fix
___
### Feature Checklist (Required for new features)
- [ ] Feature aligned with acceptance criteria
- [ ] Feature flag added (if applicable)
- [ ] Backward compatibility validated
- [ ] Performance impact assessed
- [ ] UX content copy/design validated

___
### Additional Notes / Summary of Changes, other than what's updated on JIRA
###### (What changed, why, and any risks)
RCA:

___

### Final Confidence Level

PR author confidence: (pick your honesty level) - 
- [x] High
- [ ] Medium
- [ ] Low
