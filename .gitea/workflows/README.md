The workflows in `.github/workflows` are meant for GitHub (the HACS action
needs the GitHub API). Gitea runs `.gitea/workflows` instead when this
directory exists, so its presence keeps them from running on Gitea.
