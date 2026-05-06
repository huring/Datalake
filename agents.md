# Codex Working Rules

- Always create a feature branch before implementation, even if the user does not explicitly ask for one
- Work only on that branch
- Never merge to `main` without explicit approval
- Keep prompts small and focused
- Take one task at a time
- Prefer simple practical solutions
- Avoid overengineering
- Prioritize responsiveness and simple UX
- Use lightweight structure unless complexity clearly requires more

## Git workflow

For any new feature, card, or non-trivial change:

1. Start from `main`
2. Pull latest changes
3. Create a new feature branch before making code changes
4. Do all work on that branch
5. Do not work directly on `main` unless the change is explicitly trivial
6. When the user confirms the work is complete:
   - commit any final changes
   - switch to `main`
   - merge the feature branch into `main`
   - delete the local feature branch
7. Do not merge into `main` without explicit user approval

### Branch naming

Use descriptive branch names based on the feature or card, for example:
- `feature/feature-name`
- `feature/test-name`
- `fix/auth-redirect`
- `spike/checkin`

