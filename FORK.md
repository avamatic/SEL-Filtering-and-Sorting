# Fork maintenance

This fork adds the optional DS9/Voyager AI upscale boost to Tam-Taro's complete
AIOStreams template. The template change is kept in its own commit; automation
and maintenance files are a separate fork commit.

The **Sync upstream** GitHub Actions workflow runs hourly at minute 17 (UTC),
and can also be started from the Actions page. It fetches Tam-Taro's `main`,
rebases all fork commits onto it, validates the template JSON and both upscale
controls plus their preferred/included/ranked expressions, then publishes to
this fork's `main` with an explicit force-with-lease. No access token secret is
needed: only the workflow's repository-scoped `GITHUB_TOKEN` is used.

Conflicts, validation failures, or a concurrent change to the published branch
fail the run without overwriting the feed. Review the failed run, resolve the
rebase locally, run `python3 scripts/validate-trek-patch.py`, and publish with a
lease. Do not use GitHub's **Discard commits** fork-sync option: it removes our
customization and automation.

Validate locally with:

```sh
bash -n scripts/sync-upstream.sh
python3 scripts/validate-trek-patch.py
python3 -m unittest discover -s tests -v
```

AIOStreams fetches the published fork feed hourly. Template updates are offered
for review/application; they do not automatically replace users' saved settings.
GitHub schedules may be delayed, and GitHub disables scheduled workflows in
public repositories after 60 days without repository activity. If disabled,
re-enable this workflow in Actions and run it manually.
