#!/usr/bin/env python3
"""Create a release on github with documentation assets for every version."""

import logging
import os
import re
import shutil
from itertools import groupby
from typing import NamedTuple
from pathlib import Path
from zipfile import ZipFile
import tarfile

import gitlab
from github import Github


GITLAB_SERVER = "https://gitlab.com"
GITLAB_PROJECT = "buildstream/buildstream"
GITLAB_API_TOKEN = os.getenv("GITLAB_API_TOKEN")

GITHUB_ORG_NAME = "buildstream-migration"
GITHUB_PROJECT = "buildstream"
GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN")

WORK_DIR = Path.cwd() / "work"
os.makedirs(WORK_DIR, exist_ok=True)


def main():
    """Query and download the latest pieces of BuildStream documentation."""
    logging.basicConfig(level=logging.INFO)

    versions = download_docs()
    create_tarballs(versions)
    create_github_releases(versions)


def download_docs():
    """Query and download the latest docs for every BuildStream release."""
    token = GITHUB_API_TOKEN
    g = Github(token) 
    project = g.get_repo(GITHUB_ORG_NAME + "/" + GITHUB_PROJECT)

    downloaded_versions = []

    # First, get a nicely ordered list of all tagged versions
    tags = get_semver_tags(project)
    logging.info(
        "Found the following releases on gitlab: {}".format(
            ", ".join(str(version) for version in tags)
        )
    )

    # Iterate over the tags
    for version, tag in tags.items():
        download_path = WORK_DIR / (str(version) + ".zip")
        if os.path.exists(download_path):
            downloaded_versions.append(version)
            logging.info("Already have locally downloaded docs for version: {}".format(version))
        else:
            commit = get_tag_commit(project, tag)
            if download_commit_docs(project, commit, download_path):
                downloaded_versions.append(version)
                logging.info("Downloaded docs for version: {}".format(version))
            else:
                logging.warning("Failed to download tag %s (commit %s)", tag, commit)

    return downloaded_versions


def create_tarballs(versions):
    """Convert downloaded docs zip files into tarballs."""

    # Now we can extract the docs
    for version in versions:
        # The directory in which our docs should end up
        doc_dir = WORK_DIR / str(version)

        # The zipfile containing our docs
        doc_zip = WORK_DIR / (str(version) + ".zip")

        # The tarfile to create
        doc_tar = doc_dir / "docs.tgz"

        # Convert the zips to tarballs if the tarballs are not there yet
        if not os.path.exists(doc_tar):
            logging.info("Converting {} -> {}".format(doc_zip, doc_tar))

            doc_dir.mkdir(parents=True)
            with ZipFile(doc_zip) as doc:
                doc.extractall(doc_dir)

            # Populate the tarball
            with tarfile.open(doc_tar, "w:gz") as tar:
                subdir_path = doc_dir / "public"
                subdir_path_len = len(str(subdir_path))

                for path in doc_dir.glob("public/*"):
                    pathstr = str(path)
                    arcname = pathstr[subdir_path_len:]
                    tar.add(path, arcname=arcname)

            shutil.rmtree(doc_dir / "public")


def create_github_releases(versions):
    """Create github releases for the versions and attach the docs.tgz assets."""

    git = Github(GITHUB_API_TOKEN)
    org = git.get_organization(GITHUB_ORG_NAME)
    repo = org.get_repo(GITHUB_PROJECT)

    for version in versions:

        logging.info("Creating github release: {}".format(version))

        # The directory in which our docs should end up
        doc_dir = WORK_DIR / str(version)

        # The tarfile to create
        doc_tar = doc_dir / "docs.tgz"

        # Create the release on github
        release = repo.create_git_release(str(version), str(version),
                                          "Automatically migrated release of version: {}".format(version))

        release.upload_asset(str(doc_tar), label='docs.tgz')
 

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
        return re.fullmatch(r"(\d+).(\d+).(\d+)", string)

    def __str__(self):
        """Print a Semver tuple."""
        return f"{self.major}.{self.minor}.{self.patch}"


def get_semver_tags(project):
    """Get a mapping between of tags and their semantic versions."""
    tags = project.get_tags()

    tags = [tag for tag in tags if Semver.match_semver_string(tag.name)]
    return {Semver.from_string(tag.name): tag for tag in tags}


def get_tag_commit(project, tag):
    """Get the commit of a given tag."""

    return tag.commit.sha 


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
