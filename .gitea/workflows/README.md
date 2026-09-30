`ci.yaml` runs on the Gitea pull mirror of this repository: ruff, pytest and
hassfest. Because this directory exists, Gitea ignores `.github/workflows`,
which are meant for GitHub (the HACS action needs the GitHub API).
