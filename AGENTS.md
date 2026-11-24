# IRIS implementation workflow

For every user-requested implementation:

1. Split the work into ordered, independently testable stages.
2. Start each stage with a failing regression or contract check.
3. Implement the smallest complete change for that stage.
4. Run the focused check, the relevant Iris core checks, and an actual local-model turn when the agent runtime is affected.
5. Treat any regression as a bugfix inside the current stage; do not advance until the fix and verification pass.
6. After the final stage, audit for remaining work and report it separately.

Keep the Ponytail global development rules in force throughout this workflow.
