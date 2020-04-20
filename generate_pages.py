#!/usr/bin/env python3
"""Download and deploy the latest BuildStream docs."""

import logging
import os
import re
from itertools import groupby
from typing import NamedTuple
from pathlib import Path
from zipfile import ZipFile

import gitlab


GITLAB_SERVER = "https://gitlab.com"
PROJECT = "buildstream/buildstream"
OUTPUT_DIR = Path.cwd() / "public"


def main():
    """Query and download the latest pieces of BuildStream documentation."""
    logging.basicConfig(level=logging.INFO)

    downloaded_versions = download_docs()

    # Now we can extract the docs
    for version in downloaded_versions:
        # The directory in which our docs should end up
        doc_dir = OUTPUT_DIR / str(version)
        # The zipfile containing our docs
        doc_zip = OUTPUT_DIR / (str(version) + ".zip")

        # Unzip the zipfile
        doc_dir.mkdir(parents=True)
        with ZipFile(doc_zip) as doc:
            doc.extractall(doc_dir)
        doc_zip.unlink()

        # Move the docs to the directory they're expected in
        for path in doc_dir.glob("public/*"):
            path.rename(doc_dir / path.name)

    # Finally, update the doc links
    version_tag = '<li class="toctree-l1"><a class="reference internal" href="{version}/index.html">{version}</a></li>'

    # Currently, stable versions are all even minor versions
    stable = "\n".join(version_tag.format(version=v)
                       for v in downloaded_versions if v != "master" and v.minor % 2 == 0)
    snapshot = "\n".join(version_tag.format(version=v)
                         for v in downloaded_versions if v == "master" or v.minor % 2 == 1)

    with open("index.html.tmpl") as index:
        template = index.read()

    with open(OUTPUT_DIR / "index.html", "w") as index:
        index.write(template.format(stable_versions=stable, snapshot_versions=snapshot))


def download_docs():
    """Query and download the latest pieces of BuildStream documentation."""
    token = os.getenv("API_TOKEN")
    server = gitlab.Gitlab(GITLAB_SERVER, private_token=token)
    project = server.projects.get(PROJECT)

    downloaded_versions = []

    # First, get a nicely ordered list of all minor versions
    tags = get_semver_tags(project)
    minor_groups = group_tags_by_minor_versions(tags)
    num_groups = 0

    # Next, find the latest patch version with documentation we can
    # publish and publish that documentation
    for group in minor_groups:
        num_groups += 1
        # group is a tuple of a string containing the version number
        # truncated at the minor version, and a collection of tuples
        # of semver versions and their tags that match this minor
        # version.
        #
        # E.g. ("1.2", [(Semver(1, 2, 0), <python-gitlab tag object>)])
        # *note that the collection is not a list, but a generator*
        #
        # We iterate over this in reverse order so that we pull in the
        # latest docs for the given minor version.
        versions = sorted(group[1], reverse=True)

        for version, tag in versions:
            commit = get_tag_commit(project, tag)
            if download_commit_docs(project, commit, OUTPUT_DIR / (str(version) + ".zip")):
                downloaded_versions.append(version)
                break

            logging.warning("Pipeline unsuccessful for tag %s (commit %s)", version, commit)

    # Ensure that we've found docs for exactly every minor version
    assert num_groups == len(downloaded_versions)

    # Finally, find the latest commit on master with documentation we
    # can publish
    latest = project.commits.list()[0]
    while latest:
        if download_commit_docs(project, latest, OUTPUT_DIR / "master.zip"):
            downloaded_versions.append("master")
            break

        logging.warning("Pipeline unsuccessful for commit %s - trying previous", latest.short_id)
        latest = project.commits.get(latest.parent_ids[0])

    # Ensure that we've found docs for exactly one version of master
    assert num_groups + 1 == len(downloaded_versions)

    return downloaded_versions


class Semver(NamedTuple):
    """A semantic version number."""

    major: int
    minor: int
    patch: int

    @classmethod
    def from_string(cls, string):
        """Generate a Semver tuple from a string."""
        match = cls.match_semver_string(string)
        if match:
            return Semver(*(int(num) for num in match.groups()))

        raise ValueError(f"'{string}' is not a valid semver string")

    @staticmethod
    def match_semver_string(string):
        """Test whether a Semver string is valid."""
        return re.fullmatch(r"(\d).(\d).(\d)", string)

    def __repr__(self):
        """Print a Semver tuple."""
        return f"{self.major}.{self.minor}.{self.patch}"


def get_semver_tags(project):
    """Get a mapping between of tags and their semantic versions."""
    tags = project.tags.list(all=True)

    tags = [tag for tag in tags if Semver.match_semver_string(tag.name)]
    return {Semver.from_string(tag.name): tag for tag in tags}


def group_tags_by_minor_versions(tags):
    """Get the set of latest minor versions."""
    tags = tags.items()
    tags = sorted(tags)
    # Create groups for minor versions
    return groupby(tags, lambda item: f"{item[0].major}.{item[0].minor}")


def get_tag_commit(project, tag):
    """Get the commit of a given tag."""
    return project.commits.get(tag.commit["id"])


def get_doc_job(commit):
    """Get the doc job from a commit."""

    # Search for only the "docs" job for a given commit,
    # there may be more than one "docs" job for the same
    # commit (pipeline can be run in different ways).
    #
    # Return any of these which was successful.
    #
    jobs = commit.statuses.list(name="docs")

    for job in jobs:
        if job.status == "success":
            return job
    return None


def download_commit_docs(project, commit, filename):
    """Download the docs for the given commit to the given file path."""
    job = get_doc_job(commit)
    if not job:
        return False

    docs = project.jobs.get(job.id)
    with open(filename, "wb") as output:
        docs.artifacts(streamed=True, action=output.write)
    return True


if __name__ == "__main__":
    main()
