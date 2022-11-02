#!/usr/bin/env python3
import os
import logging
import re
import itertools
import urllib.request
import urllib.error
import tarfile
from typing import NamedTuple
from github import Github
from pathlib import Path


GITHUB_ORG_NAME = "buildstream-migration"
GITHUB_PROJECT = "buildstream"
GITHUB_API_TOKEN = os.getenv("API_TOKEN")

WORK_DIR = Path.cwd() / "work"
OUTPUT_DIR = Path.cwd() / "public"
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def main():
    logging.basicConfig(level=logging.INFO)

    git = Github(GITHUB_API_TOKEN)
    org = git.get_organization(GITHUB_ORG_NAME)
    repo = org.get_repo(GITHUB_PROJECT)

    # Query github and find out which GitRelease objects we're interested in.
    #
    stable_releases, dev_snapshots = select_releases(repo)

    # Download the docs and extract them into the site directory for
    # each github GitRelease we're interested in.
    #
    for version, release in stable_releases + dev_snapshots:
        download_and_extract_docs(version, release)

    # Format the template
    #
    version_tag = '<li class="toctree-l1"><a class="reference internal" href="{version}/index.html">{version}</a></li>'
    stable = "\n".join(version_tag.format(version=v) for v, _ in stable_releases)
    snapshot = "\n".join(version_tag.format(version=v) for v, _ in dev_snapshots)

    with open("index.html.tmpl") as index:
        template = index.read()

    with open(OUTPUT_DIR / "index.html", "w") as index:
        index.write(template.format(stable_versions=stable, snapshot_versions=snapshot))


def select_releases(repo):
    """"Iterates over all the releases and selects the latest releases

    Args:
       repo (GitRepo): The GitRepo to query for releases

    Returns:
       (list): A list of (Semver, GitRelease) tuples for each selected stable release
       (list): A list of (Semver, GitRelease) tuples for each selected dev snapshot
    """
    releases = {}

    # First get all the releases and populate a table of them, indexed by Semver
    #
    for release in repo.get_releases():
        try:
            version = Semver.from_string(release.tag_name)
        except VersionError:
            # If the Release could not derive the version from the
            # tag, then it's some kind of invalid noise in the github
            # releases, just ignore any release not associated to a
            # Semver formatted release tag.
            #
            continue

        releases[version] = release

    # Now group the releases by minor point
    #
    grouped_releases = group_releases_by_minor_versions(releases)

    # Lets just print out the releases we found
    #
    logging.info("Found the following releases:")
    for group, releases in grouped_releases.items():
        logging.info("  Group {}.{}".format(group[0], group[1]))
        for release in releases:
            logging.info("    Release: {}".format(release[0]))

    # Now lets select which releases we want to use for docs
    #
    stable_releases = []
    dev_snapshots = []

    # Build a list of tuples for the latest release of each series,
    # separated by stable release (even minor point) and dev snapshot (odd minor point)
    #
    for group, releases in grouped_releases.items():

        # If it's a stable release, add the latest one from the group to the list of stable releases,
        # otherwise append the latest of this dev snapshot to the list of snapshots
        if group[1] % 2 == 0:
            stable_releases.append(releases[-1])
        else:
            dev_snapshots.append(releases[-1])

    # We only care about publishing the latest dev snapshot, the older
    # snaphot serieses are not relevant as they will have had stable
    # releases by now.
    #
    dev_snapshot = dev_snapshots[-1]

    # Lets print what we've selected
    #
    logging.info("\nSelected the following stable releases:")
    for release_version, _ in stable_releases:
        logging.info("  Release: {}".format(release_version))

    logging.info("\nSelected the following dev snapshot:")
    logging.info("  Snapshot: {}".format(dev_snapshot[0]))

    return stable_releases, [ dev_snapshot ]


def group_releases_by_minor_versions(releases):
    """Get the set of latest minor versions.

    Args:
       releases (dict): A dictionary of GitRelease objects, indexed by Semver object

    Returns:
       (dict): A dictionary of sorted lists of the format [(Semver, GitRelease)], indexed by
               (int, int) major/minor point version tuples.

    Because python guarantees the preservation of the order of dictionary keys
    by their insertion order, the returned dictionary is also guaranteed to be
    sorted from lowest release to greatest release.

    The lists of releases per major/minor point tuple are also sorted, the
    last item in each list is the latest release for the given set.
    """

    # Change this dictionary into a list of tuples of (Semver, GitRelease)
    releases = releases.items()

    # Lets sort the tuples by Semver
    releases = sorted(releases)

    # Create groups for minor versions, this will give us a list of tuples, where
    # the first element is a major.minor point version (group) and the second
    # tuple element is the list of (Semver, GitRelease) tuples associated to that
    # version.
    #
    groups = itertools.groupby(releases, lambda item: (item[0].major, item[0].minor))

    # Now lets construct a new dictionary of these groups, and sort the lists for
    # a more convenient return.
    #
    grouped_releases = {}
    for group in groups:
        group_version = group[0]
        group_versions = group[1]
        grouped_releases[group_version] = sorted(group_versions)

    return grouped_releases


def download_and_extract_docs(version, release):
    """Downloads and extracts the documentation for the given release.

    Args:
       version (Semver): The version we're extracting docs for
       release (GitRelease): The github release object
    """
    logging.info("Downloading docs for version: {}".format(version))

    download_path = os.path.join(WORK_DIR, "docs-{}.tgz".format(version))
    extract_path = os.path.join(OUTPUT_DIR, str(version))

    for asset in release.get_assets():
        if asset.name == "docs.tgz":
            download_asset(asset.browser_download_url, download_path)

    if not os.path.exists(download_path):
        logging.error("Could not download docs for version: {}".format(version))

    with tarfile.open(download_path, "r:*") as tar:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tar, path=extract_path)


def download_asset(url, filename):
    logging.info("Downloading {} as {}".format(url, filename))
    response = urllib.request.urlopen(url)
    data = response.read()
    with open(filename, "wb") as f:
        f.write(data)


class VersionError(ValueError):
    """The version string parsed by Semver is invalid"""
    pass


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

        raise VersionError(f"'{string}' is not a valid semver string")

    @staticmethod
    def match_semver_string(string):
        """Test whether a Semver string is valid."""
        return re.fullmatch(r"(\d+).(\d+).(\d+)", string)

    def __lt__(self, other):
        """Compare a Semver to another Semver for sorting purposes"""
        if self.major < other.major:
            # Lower major point
            return True
        elif self.major == other.major:
            if self.minor < other.minor:
                # Equal major point and lower minor point
                return True
            elif self.minor == other.minor:
                if self.patch < other.patch:
                    # Equal major and minor point, lower patch level.
                    return True

        return False

    def __str__(self):
        """Print a Semver tuple."""
        return f"{self.major}.{self.minor}.{self.patch}"


if __name__ == "__main__":
    main()
