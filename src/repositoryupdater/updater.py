"""Bringing an apps repository up to date with the apps it lists."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

from .appconfig import AppDetails, parse_config, render_config
from .applist import AppEntry, AppList, ChangelogMode, Channel, parse_app_list
from .archive import app_files
from .cache import CachedApp, git_blob_sha, read_cache, write_cache
from .const import (
    APP_LIST_FILENAMES,
    CONFIG_FILENAMES,
    README_TEMPLATE,
    STATIC_DIRECTORIES,
    STATIC_FILES,
)
from .exceptions import (
    AppConfigNotFoundError,
    AppNotFoundError,
    AppReleaseNotFoundError,
    AppsFailedError,
    AppVersionNotFoundError,
    InvalidAppConfigError,
    RepositoryAppListNotFoundError,
    RepositoryUpdaterError,
)
from .github import (
    GitHubAuthenticationError,
    GitHubConflictError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
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

# Errors that would hit every app the same way, or a branch that moved under
# this run, whose snapshot is no good anymore; no use carrying on.
STOP_THE_RUN = (GitHubAuthenticationError, GitHubConflictError, GitHubRateLimitError)

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
    # The app's own repository, which the READMEs link to.
    repository: Repository


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
    updating: bool
    # The app's own repository; None when even that could not be found.
    repository: Repository | None = None
    # None if the apps repository never held this app.
    current: AppState | None = None
    # Only looked up for apps in this run.
    latest: LatestState | None = None
    # What went wrong with this app, if anything. When it went wrong before
    # its current state was known, the README cannot show it this run.
    error: RepositoryUpdaterError | None = None
    current_known: bool = True
    # The blob SHA of the app's configuration in the apps repository.
    config_sha: str | None = None
    from_cache: bool = False
    # A version the apps repository holds, but its own repository no longer
    # knows. The app can still get an update; until then, the README cannot
    # show it.
    lost_version: str | None = None

    @property
    def target(self) -> str:
        """Return this app's directory inside the apps repository."""
        return self.entry.repository_target

    def needs_update(self, latest: LatestState, *, force: bool) -> bool:
        """Return whether the apps repository is behind on this app."""
        current = self.current.version if self.current else None
        return needs_update(current, latest.version, force=force)

    def update_to(self, *, force: bool) -> LatestState | None:
        """Return the version to update this app to, if it gets an update."""
        if self.error is not None or self.latest is None:
            return None

        if not self.needs_update(self.latest, force=force):
            return None

        return self.latest


@dataclass(kw_only=True)
class Run:
    """What one run works with, once the apps repository is known."""

    repository: Repository
    user: User
    app_list: AppList
    # The commit of the apps repository this run works from; it moves along
    # with every commit the run makes.
    head: str
    # Every file in the apps repository at that commit, with its blob SHA.
    blobs: dict[str, str]
    readme_template: bytes | None
    apps: list[App] = field(default_factory=list)
    # Apps that got their update in this run; the README shows those at
    # their new version.
    published: set[str] = field(default_factory=set)

    @property
    def readme(self) -> bool:
        """Return whether the README can show every app.

        When an app could not be read, the README stays as it is, rather
        than dropping that app; the next run catches it up.
        """
        return all(
            app.current_known or app.target in self.published for app in self.apps
        )


@dataclass(kw_only=True)
class Updater:
    """Brings one apps repository up to date with the apps it lists."""

    github: GitHub
    output: Output
    repository_name: str
    app_filter: str | None = None
    force: bool = False
    dry_run: bool = False
    # Where the cache of this apps repository lives; None runs without one.
    cache_path: Path | None = None

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

        self._check_filter(app_list)

        head = await self.github.branch_head(
            repository.full_name, repository.default_branch
        )
        run = Run(
            repository=repository,
            user=user,
            app_list=app_list,
            head=head,
            blobs=await self.github.tree(repository.full_name, head),
            readme_template=await self.github.file(
                repository.full_name, README_TEMPLATE
            ),
        )
        cached = read_cache(self.cache_path) if self.cache_path else {}
        run.apps = await self._load_apps(run, cached)
        self._report(run.apps, app_list.channel)

        if not run.readme:
            self.output.warning(
                "The README of the apps repository stays as it is this run: "
                "not every app could be read."
            )

        self.output.divider()
        await self._commit(run, README_COMMIT_MESSAGE, self._readme(run))

        for app in run.apps:
            latest = app.update_to(force=self.force)
            if latest is not None:
                await self._publish(run, app, latest)

        self.output.end_section()
        self._save_cache(run.apps)
        self._raise_failures(run.apps)

    async def _publish(self, run: Run, app: App, latest: LatestState) -> None:
        """Commit the update of one app; when it fails, the app keeps its error."""
        self.output.section(f"Updating app {self.output.plain(app.target)}")
        try:
            files = await self._app_files(app, latest, run)

            run.published.add(app.target)
            files |= self._readme(run)

            message = commit_message(
                latest.details.name, latest.version, forced=self.force
            )
            committed = await self._commit(run, message, files)
        except STOP_THE_RUN:
            raise
        except RepositoryUpdaterError as error:
            # Nothing of this app got committed; the README keeps it at the
            # version it has.
            run.published.discard(app.target)
            app.error = error
            self.output.error(str(error))
            return

        if committed:
            # The apps repository holds the new version now; the cache
            # remembers it with the configuration just written.
            config = files[f"{app.target}/{latest.config_filename}"]
            app.current = latest
            app.current_known = True
            app.config_sha = git_blob_sha(config) if config is not None else None

    def _save_cache(self, apps: list[App]) -> None:
        """Remember what the apps repository holds of every app it could read."""
        if self.cache_path is None:
            return

        entries = {
            app.target: CachedApp(
                source=app.entry.repository,
                config_filename=app.current.config_filename,
                config_sha=app.config_sha,
                repository=app.current.repository,
                version=app.current.version.version,
                commit=app.current.version.commit,
                details=app.current.details,
            )
            for app in apps
            if app.current is not None and app.config_sha is not None
        }
        try:
            write_cache(self.cache_path, entries)
        except OSError as error:
            self.output.warning(
                f"Could not write the cache: {self.output.plain(error)}"
            )

    def _raise_failures(self, apps: list[App]) -> None:
        """Report every app that failed, and fail the run when there are any."""
        failed = [app for app in apps if app.error is not None]
        if not failed:
            return

        self.output.divider()
        for app in failed:
            self.output.error(f"App {app.target}: {app.error}")
        raise AppsFailedError([app.target for app in failed])

    def _check_filter(self, app_list: AppList) -> None:
        """Refuse an app to update that the app list does not have."""
        if self.app_filter and not any(
            self._is_selected(entry) for entry in app_list.apps
        ):
            raise AppNotFoundError(self.app_filter)

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

    async def _load_apps(self, run: Run, cached: dict[str, CachedApp]) -> list[App]:
        """Load every app in the list, a handful at a time."""
        entries = run.app_list.apps
        self.output.info(f"Loading {len(entries)} apps")
        limit = asyncio.Semaphore(PARALLEL_LOADS)

        async def load(entry: AppEntry) -> App:
            async with limit:
                return await self._load_app(
                    run, entry, cached.get(entry.repository_target)
                )

        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(load(entry)) for entry in entries]
        except* RepositoryUpdaterError as errors:
            # Only errors that hit every app get here; the rest got cancelled.
            raise errors.exceptions[0] from None

        apps = [task.result() for task in tasks]
        from_cache = sum(app.from_cache for app in apps)
        if from_cache:
            self.output.info(f"{from_cache} of them from the cache")
        return apps

    async def _load_app(
        self, run: Run, entry: AppEntry, cached: CachedApp | None
    ) -> App:
        """Load what the apps repository holds of an app, and what is out.

        An app that fails keeps its error, so the other apps carry on.
        """
        app = App(entry=entry, updating=self._is_selected(entry))
        try:
            repository = self._from_cache(app, run.blobs, cached)
            if repository is None:
                repository = await self.github.repository(entry.repository)
                app.repository = repository
                await self._load_current(app, repository, run.blobs)
        except STOP_THE_RUN:
            raise
        except RepositoryUpdaterError as error:
            app.error = error
            app.current_known = False
            return app

        if app.updating:
            try:
                await self._load_latest(app, repository, run.app_list.channel)
            except STOP_THE_RUN:
                raise
            except RepositoryUpdaterError as error:
                app.error = error

        return app

    @staticmethod
    def _config_filename(target: str, blobs: Mapping[str, str]) -> str | None:
        """Return the configuration file an app has in the apps repository."""
        return next(
            (name for name in CONFIG_FILENAMES if f"{target}/{name}" in blobs), None
        )

    def _from_cache(
        self, app: App, blobs: Mapping[str, str], cached: CachedApp | None
    ) -> Repository | None:
        """Take what the cache has of an app, if it still matches the repository.

        Returns the app's own repository when the cache was used.
        """
        if cached is None or cached.source != app.entry.repository:
            return None

        filename = self._config_filename(app.target, blobs)
        if filename != cached.config_filename:
            return None

        if blobs[f"{app.target}/{filename}"] != cached.config_sha:
            return None

        app.repository = cached.repository
        app.config_sha = cached.config_sha
        app.from_cache = True
        app.current = AppState(
            version=AppVersion(version=cached.version, commit=cached.commit),
            details=cached.details,
            config_filename=filename,
            repository=cached.repository,
        )
        return cached.repository

    async def _load_current(
        self, app: App, repository: Repository, blobs: Mapping[str, str]
    ) -> None:
        """Load the version of an app the apps repository holds now."""
        filename = self._config_filename(app.target, blobs)
        if filename is None:
            return

        path = f"{app.target}/{filename}"
        location = f"{self.repository_name}/{path}"
        content = await self.github.file(self.repository_name, path)
        if content is None:
            # Gone since the listing; not knowing beats dropping the app.
            raise AppConfigNotFoundError(location)

        config = parse_config(location, content)
        if "version" not in config:
            raise InvalidAppConfigError(location, 'it is missing "version"')

        version = str(config["version"])
        try:
            found = await self._find_version(app.entry.repository, version)
        except AppVersionNotFoundError:
            app.lost_version = version
            app.current_known = False
            return

        app.config_sha = blobs[path]
        app.current = AppState(
            version=found,
            details=AppDetails.from_config(location, config),
            config_filename=filename,
            repository=repository,
        )

    async def _find_version(self, repository: str, version: str) -> AppVersion:
        """Find the commit behind a version an apps repository holds."""
        for ref in version_refs(version):
            try:
                commit = await self.github.commit(repository, ref)
            except GitHubNotFoundError:
                continue
            return AppVersion(version=version, commit=commit)

        raise AppVersionNotFoundError(repository, version)

    async def _load_latest(
        self, app: App, app_repository: Repository, channel: Channel
    ) -> None:
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
            repository=app_repository,
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
            if app.repository is not None:
                self.output.info(
                    f"Source: {self.output.plain(app.repository.html_url)}"
                )

            if app.lost_version is not None:
                current = (
                    f"{self.output.highlight(app.lost_version)} "
                    f"{self.output.emphasis('(not found in its repository)')}"
                )
            elif app.current is None:
                current = self.output.emphasis("Not available")
            else:
                version = app.current.version
                current = (
                    f"{self.output.highlight(version.version)} "
                    f"({version.commit.sha[:7]})"
                )
            self.output.info(f"Current version: {current}")

            if app.error is not None:
                self.output.warning(f"Skipping: {self.output.plain(app.error)}")
                continue

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
            repository=state.repository,
        )

    def _readme(self, run: Run) -> Files:
        """Return the README of the apps repository, if it gets one this run."""
        if run.readme_template is None or not run.readme:
            return {}

        channel = run.app_list.channel
        states = [
            (app, app.latest if app.target in run.published else app.current)
            for app in run.apps
        ]
        data = repository_template_data(
            repository=run.repository,
            channel=channel,
            apps=[
                self._template_data(app, state, channel)
                for app, state in states
                if state is not None
            ],
        )
        readme = render_template(
            run.readme_template,
            data,
            location=f"{run.repository.full_name}/{README_TEMPLATE}",
        )
        return {"README.md": readme.encode()}

    async def _app_files(self, app: App, latest: LatestState, run: Run) -> Files:
        """Return every file an update of an app writes, or deletes."""
        filename = latest.config_filename
        paths = run.blobs

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
                source[README_TEMPLATE],
                self._template_data(app, latest, run.app_list.channel),
                location=f"{app.entry.repository}/{app.entry.app_target}/{README_TEMPLATE}",
            ).encode()

        changelog = await self._changelog(app, latest, run.app_list.changelog)
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

    async def _commit(self, run: Run, message: str, files: Files) -> bool:
        """Commit files to the apps repository; in a dry run, show the diff.

        Returns whether the apps repository holds these files now, which a
        dry run never makes so.
        """
        self.output.step(f"Committing {self.output.plain(message)}")

        if self.dry_run:
            changed = await self._changed_paths(run.repository, files)
            if not changed:
                self.output.skipped("Skipped, no changes.")
                return False

            self.output.done("Would commit (dry run):")
            for path, change in sorted(changed.items()):
                self.output.info(f"  {change}: {self.output.plain(path)}")
            return False

        commit = await self.github.commit_files(
            run.repository.full_name,
            branch=run.repository.default_branch,
            message=message,
            files=files,
            author=run.user,
            expected_head=run.head,
        )
        if commit is None:
            self.output.skipped("Skipped, no changes.")
        else:
            run.head = commit.sha
            self.output.done(f"Done: {commit.sha[:7]}")
        return True

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
