## What and why

<!-- One or two sentences. Link the roadmap item, e.g. "M2: image.inspect tool". -->

## Checklist

- [ ] Tests added/updated and passing (`python -m unittest discover -s tests -t .`)
- [ ] `ruff check src tests && ruff format --check src tests` clean
- [ ] No new tool exposes shell, network or arbitrary filesystem access
- [ ] Originals are not overwritten by default
- [ ] No secrets, personal photos or personal data added
- [ ] Upstream (Image Toolbox, Apache-2.0) code reused? If yes, licence header + NOTICE kept
- [ ] CHANGELOG.md updated
