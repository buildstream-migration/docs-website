#!/usr/bin/env python3
import os
import logging
import re
from typing import NamedTuple
from github import Github
from packaging import version
from pathlib import Path

GITHUB_ORG_NAME = "buildstream-migration"
GITHUB_PROJECT = "buildstream"
GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN")

WORK_DIR = Path.cwd() / "work"
os.makedirs(WORK_DIR, exist_ok=True)

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

def get_latest():
    """Query and download the latest pieces of BuildStream documentation."""
    logging.basicConfig(level=logging.INFO)

    git = Github(GITHUB_API_TOKEN)
    org = git.get_organization(GITHUB_ORG_NAME)
    repo = org.get_repo(GITHUB_PROJECT)
    release = "0.0.0"
    snapshot = "0.0.0"

    # index.html is at the root of the tarball
    for releasetag in repo.get_releases():
        tuple_version = Semver.from_string(releasetag.title)
        
        if (tuple_version.minor % 2 == 0):
            if version.parse(releasetag.title) > version.parse(release):
                release = releasetag.title
        else:
            if version.parse(releasetag.title) > version.parse(snapshot):
                snapshot = releasetag.title

    return(release, snapshot)

def download_doc(version):
    # this should take a version tag, get the commit for that tag, and download the 
    # associated artifact from the docs job. I still can't find a means to do this via
    # the API from github.

    pass


def main():
    # At the moment, this just prints the most release and snapshot versions. Once
    # download_doc() is working, we can pass the output of get_latest() into it and it
    # should download and save the doc.tgz for each. We can then generate the webpage
    # from those docs.
    print(get_latest())

if __name__ == "__main__":
    main()
