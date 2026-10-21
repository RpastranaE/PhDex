# PhDex: development

- Use synthetic fixtures for tests. Do not commit personal state, databases, scientific documents, credentials, logs or backups.
- Preserve originals and reject filename collisions. Keep path validation and RAW acquisition safeguards.
- User state belongs in the Windows Documents folder and must survive executable updates.
- Run the Python and JavaScript tests after functional changes. Build the Windows executable and run both executable smoke checks before a release.
- Keep the app guide and release documentation aligned with the implemented behavior.
