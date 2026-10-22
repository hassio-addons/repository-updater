"""Bringing an apps repository up to date with the apps it lists."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .appconfig import AppDetails, parse_config, render_config
from .applist import AppEntry, AppList, ChangelogMode, Channel, parse_app_list
from .archive import app_files
from .const import (
    APP_LIST_FILENAMES,
    CONFIG_FILENAMES,
    README_TEMPLATE,
    STATIC_DIRECTORIES,
    STATIC_FILES,
)
from .exceptions import (
    AppConfigNotFoundError,
    AppReleaseNotFoundError,
    AppVersionNotFoundError,
    InvalidAppConfigError,
    RepositoryAppListNotFoundError,
    RepositoryUpdaterError,
)
from .github import GitHubNotFoundError
from .render import (
    README_COMMIT_MESSAGE,
    app_template_data,
    commit_message,
    prepend_changelog,
    render_changelog,
    render_template,
    repository_template_data,
)
from .versions import (
    AppVersion,
    needs_update,
    pick_latest,
    pick_release,
    version_refs,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .github import GitHub, Release, Repository, User
    from .output import Output

# How many apps load at the same time. Enough to be quick, few enough to
# stay clear of GitHub's secondary rate limits.
PARALLEL_LOADS = 8

Files = dict[str, bytes | None]


@dataclass(frozen=True, kw_only=True)
class AppState:
    """A version of an app, and the details its configuration gives."""

    version: AppVersion
    details: AppDetails
    # The configuration file it came from, like config.yaml.
    config_filename: str


@dataclass(frozen=True, kw_only=True)
class LatestState(AppState):
    """The version of an app its channel publishes now."""

    config: dict[str, Any]
    # The newest release the channel may publish. On edge, the changelog of
    # a commit lists everything since this one.
    release: Release | None


@dataclass(kw_only=True)
class App:
    """One app from the list: what the apps repository has, and what is out."""

    entry: AppEntry
    repository: Repository
    updating: bool
    # None if the apps repository never held this app.
    current: AppState | None = None
    # Only looked up for apps in this run.
    latest: LatestState | None = None

    @property
    def target(self) -> str:
        """Return this app's directory inside the apps repository."""
        return self.entry.repository_target

    def needs_update(self, latest: LatestState, *, force: bool) -> bool:
        """Return whether the apps repository is behind on this app."""
        current = self.current.version if self.current else None
        return needs_update(current, latest.version, force=force)


@dataclass(kw_only=True)
class Updater:
    """Brings one apps repository up to date with the apps it lists."""

    github: GitHub
    output: Output
    repository_name: str
    app_filter: str | None = None
    force: bool = False
    dry_run: bool = False

    async def run(self) -> None:
        """Load everything, then commit the README and every app update."""
        user = await self.github.user()
        self.output.info(
            f"Authenticated with GitHub as {self.output.emphasis(user.commit_name)}"
        )

        self.output.step(
            f'Locating apps repository "{self.output.emphasis(self.repository_name)}"'
        )
        repository = await self.github.repository(self.repository_name)
        self.output.done("Found!")

        app_list = await self._app_list(repository)
        self.output.info(
            f"Repository channel: {self.output.highlight(app_list.channel)}"
        )
        if self.app_filter:
            self.output.warning(
                f'Only updating app "{self.output.plain(self.app_filter)}" this run!'
            )

        apps = await self._load_apps(app_list)
        self._report(apps, app_list.channel)

        paths = set(
            await self.github.tree(repository.full_name, repository.default_branch)
        )
        readme_template = await self.github.file(repository.full_name, README_TEMPLATE)

        # Apps that got their update in this run; the README shows those at
        # their new version.
        published: set[str] = set()

        self.output.divider()
        await self._commit(
            repository,
            user,
            README_COMMIT_MESSAGE,
            self._readme(
                repository, app_list.channel, apps, published, readme_template
            ),
        )

        for app in apps:
            if app.latest is None or not app.needs_update(app.latest, force=self.force):
                continue

            self.output.section(f"Updating app {self.output.plain(app.target)}")
            files = await self._app_files(app, app.latest, app_list, paths)

            published.add(app.target)
            files |= self._readme(
                repository, app_list.channel, apps, published, readme_template
            )

            message = commit_message(
                app.latest.details.name, app.latest.version, forced=self.force
            )
            await self._commit(repository, user, message, files)

    async def _app_list(self, repository: Repository) -> AppList:
        """Fetch and parse the app list the apps repository declares."""
        self.output.step("Locating repository app list")

        for filename in APP_LIST_FILENAMES:
            content = await self.github.file(repository.full_name, filename)
            if content is None:
                continue

            try:
                app_list = parse_app_list(filename, content)
            except RepositoryUpdaterError:
                self.output.failed()
                raise

            self.output.done("Loaded!")
            return app_list

        self.output.failed()
        raise RepositoryAppListNotFoundError(APP_LIST_FILENAMES)

    async def _load_apps(self, app_list: AppList) -> list[App]:
        """Load every app in the list, a handful at a time."""
        self.output.info(f"Loading {len(app_list.apps)} apps")
        limit = asyncio.Semaphore(PARALLEL_LOADS)

        async def load(entry: AppEntry) -> App:
            async with limit:
                return await self._load_app(app_list.channel, entry)

        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(load(entry)) for entry in app_list.apps]
        except* RepositoryUpdaterError as errors:
            # The first app that failed stops the run; the rest got cancelled.
            raise errors.exceptions[0] from None

        return [task.result() for task in tasks]

    async def _load_app(self, channel: Channel, entry: AppEntry) -> App:
        """Load what the apps repository holds of an app, and what is out."""
        app = App(
            entry=entry,
            repository=await self.github.repository(entry.repository),
            updating=self._is_selected(entry),
        )
        await self._load_current(app)

        if app.updating:
            await self._load_latest(app, channel)

        return app

    async def _load_current(self, app: App) -> None:
        """Load the version of an app the apps repository holds now."""
        for filename in CONFIG_FILENAMES:
            path = f"{app.target}/{filename}"
            content = await self.github.file(self.repository_name, path)
            if content is None:
                continue

            location = f"{self.repository_name}/{path}"
            config = parse_config(location, content)
            if "version" not in config:
                raise InvalidAppConfigError(location, 'it is missing "version"')

            app.current = AppState(
                version=await self._find_version(
                    app.entry.repository, str(config["version"])
                ),
                details=AppDetails.from_config(location, config),
                config_filename=filename,
            )
            return

    async def _find_version(self, repository: str, version: str) -> AppVersion:
        """Find the commit behind a version an apps repository holds."""
        for ref in version_refs(version):
            try:
                commit = await self.github.commit(repository, ref)
            except GitHubNotFoundError:
                continue
            return AppVersion(version=version, commit=commit)

        raise AppVersionNotFoundError(repository, version)

    async def _load_latest(self, app: App, channel: Channel) -> None:
        """Load the version of an app its channel publishes now."""
        repository = app.entry.repository

        release = pick_release(await self.github.releases(repository), channel)
        release_commit = (
            await self.github.commit(repository, release.tag_name) if release else None
        )
        head = (
            await self.github.latest_commit(repository)
            if channel is Channel.EDGE
            else None
        )

        latest = pick_latest(
            channel, release=release, release_commit=release_commit, head=head
        )
        if latest is None:
            raise AppReleaseNotFoundError(repository, channel)

        filename, config = await self._latest_config(app, latest)
        app.latest = LatestState(
            version=latest,
            details=AppDetails.from_config(
                f"{repository}/{app.entry.app_target}/{filename}", config
            ),
            config_filename=filename,
            config=config,
            release=release,
        )

    async def _latest_config(
        self, app: App, latest: AppVersion
    ) -> tuple[str, dict[str, Any]]:
        """Fetch the configuration of an app at the version being published."""
        # Look for the format the apps repository has first.
        current = app.current.config_filename if app.current else None
        filenames = sorted(CONFIG_FILENAMES, key=lambda filename: filename != current)
        for filename in filenames:
            path = f"{app.entry.app_target}/{filename}"
            content = await self.github.file(
                app.entry.repository, path, ref=latest.commit.sha
            )
            if content is not None:
                return filename, parse_config(f"{app.entry.repository}/{path}", content)

        location = (
            f"{app.entry.repository}/{app.entry.app_target} at {latest.commit.sha[:7]}"
        )
        raise AppConfigNotFoundError(location)

    def _is_selected(self, entry: AppEntry) -> bool:
        """Return whether an app is in scope for this run."""
        if not self.app_filter:
            return True
        return self.app_filter in {entry.repository_target, entry.repository}

    def _report(self, apps: list[App], channel: Channel) -> None:
        """Show what was found for every app, in the order of the list."""
        for app in apps:
            self.output.section(f"App {self.output.plain(app.target)}")
            self.output.info(f"Source: {self.output.plain(app.repository.html_url)}")

            if app.current is None:
                current = self.output.emphasis("Not available")
            else:
                version = app.current.version
                current = (
                    f"{self.output.highlight(version.version)} "
                    f"({version.commit.sha[:7]})"
                )
            self.output.info(f"Current version: {current}")

            if app.latest is None:
                continue

            latest = app.latest.version
            self.output.info(
                f"Latest {channel} version: "
                f"{self.output.highlight(latest.version)} "
                f"({latest.commit.sha[:7]})"
            )
            if app.needs_update(app.latest, force=False):
                self.output.warning("This app has an update waiting to be published!")
            else:
                self.output.success("This app is up to date.")

        self.output.end_section()
        self.output.success("Done loading all repository apps")

    @staticmethod
    def _template_data(app: App, state: AppState, channel: Channel) -> dict[str, Any]:
        """Return the template data of an app at a version."""
        return app_template_data(
            entry=app.entry,
            channel=channel,
            details=state.details,
            version=state.version,
            repository=app.repository,
        )

    def _readme(
        self,
        repository: Repository,
        channel: Channel,
        apps: list[App],
        published: set[str],
        template: bytes | None,
    ) -> Files:
        """Return the README of the apps repository, if it has a template."""
        if template is None:
            return {}

        states = [
            (app, app.latest if app.target in published else app.current)
            for app in apps
        ]
        data = repository_template_data(
            repository=repository,
            channel=channel,
            apps=[
                self._template_data(app, state, channel)
                for app, state in states
                if state is not None
            ],
        )
        return {"README.md": render_template(template.decode(), data).encode()}

    async def _app_files(
        self, app: App, latest: LatestState, app_list: AppList, paths: set[str]
    ) -> Files:
        """Return every file an update of an app writes, or deletes."""
        filename = latest.config_filename

        self.output.step("Downloading app source")
        tarball = await self.github.tarball(
            app.entry.repository, latest.version.commit.sha
        )
        source = app_files(app.entry.repository, tarball, app.entry.app_target)
        self.output.done()

        files: Files = {}

        # The configuration, in the format the app uses, and no other.
        files[f"{app.target}/{filename}"] = render_config(
            filename,
            latest.config,
            version=latest.version.version,
            image=app.entry.image,
        ).encode()
        for other in CONFIG_FILENAMES:
            if other != filename and f"{app.target}/{other}" in paths:
                files[f"{app.target}/{other}"] = None

        # Static files follow the source: copied when there, gone when not.
        for name in STATIC_FILES:
            path = f"{app.target}/{name}"
            if name in source:
                files[path] = source[name]
            elif path in paths:
                files[path] = None

        for directory in STATIC_DIRECTORIES:
            copied = {
                f"{app.target}/{name}": content
                for name, content in source.items()
                if name.startswith(f"{directory}/")
            }
            files |= copied
            files |= {
                path: None
                for path in paths
                if path.startswith(f"{app.target}/{directory}/") and path not in copied
            }

        # A README template beats a README.md copied from the source.
        if README_TEMPLATE in source:
            files[f"{app.target}/README.md"] = render_template(
                source[README_TEMPLATE].decode(),
                self._template_data(app, latest, app_list.channel),
            ).encode()

        changelog = await self._changelog(app, latest, app_list.changelog)
        files[f"{app.target}/CHANGELOG.md"] = changelog.encode()
        return files

    async def _changelog(
        self, app: App, latest: LatestState, mode: ChangelogMode
    ) -> str:
        """Return the changelog of the version of an app being published."""
        version = latest.version
        if version.is_release:
            notes = render_changelog(version)
            if mode is ChangelogMode.REPLACE:
                return notes

            existing = await self.github.file(
                self.repository_name, f"{app.target}/CHANGELOG.md"
            )
            return prepend_changelog(
                existing.decode() if existing else "",
                notes,
                version=version.version,
                previous_version=app.current.version.version if app.current else None,
            )

        # Edge publishes commits; their changelog always replaces the file.
        if latest.release is None:
            return render_changelog(version)

        commits = await self.github.compare(
            app.entry.repository, latest.release.tag_name, version.commit.sha
        )
        return render_changelog(version, since=latest.release, commits=commits)

    async def _commit(
        self, repository: Repository, user: User, message: str, files: Files
    ) -> None:
        """Commit files to the apps repository; in a dry run, show the diff."""
        self.output.step(f"Committing {self.output.plain(message)}")

        if self.dry_run:
            changed = await self._changed_paths(repository, files)
            if not changed:
                self.output.skipped("Skipped, no changes.")
                return

            self.output.done("Would commit (dry run):")
            for path, change in sorted(changed.items()):
                self.output.info(f"  {change}: {self.output.plain(path)}")
            return

        commit = await self.github.commit_files(
            repository.full_name,
            branch=repository.default_branch,
            message=message,
            files=files,
            author=user,
        )
        if commit is None:
            self.output.skipped("Skipped, no changes.")
        else:
            self.output.done(f"Done: {commit.sha[:7]}")

    async def _changed_paths(
        self, repository: Repository, files: Mapping[str, bytes | None]
    ) -> dict[str, str]:
        """Return which files would change, and how, without committing."""
        changed: dict[str, str] = {}
        for path, content in files.items():
            current = await self.github.file(repository.full_name, path)
            # Only files that are there get deleted.
            if content is None:
                changed[path] = "delete"
            elif current is None:
                changed[path] = "add"
            elif current != content:
                changed[path] = "change"
        return changed
