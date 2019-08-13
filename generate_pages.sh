#!/bin/sh
# Small script which fetches all the tags from the BuildStream repository,
# downloads all the documentation artifacts and then creates a list of the
# links in the index.html.

# This line is always present in the index.html so that we can automatically
# create the list of tags.
stable_line="<!-- Change this line with the list of available STABLE versions. -->"
snapshot_line="<!-- Change this line with the list of available SNAPSHOT versions. -->"

# Versions we shouldn't fetch as their artifacts are not found similar to the others or
# non existing at all.
unavailable_versions="1.1.7"

# Lists of href's we'll insert into index.html
stable_tags=""
snapshot_tags=""

# We need to automatically update the badges, so find the latest release and
# latest stable we have.
latest_release=""
latest_snapshot=""
BST_REPO="https://gitlab.com/BuildStream/buildstream"

# Fetch all the tags and parse them.
tags=$(git ls-remote --tags ${BST_REPO} | awk -F[/\^] '{print $3}' | uniq | grep [0-9]\.[0-9]\.[0-9] | tac | grep -v ${unavailable_versions})
major_minors=$(git ls-remote --tags ${BST_REPO} | awk -F[/\^] '{print $3}' | uniq | grep [0-9]\.[0-9]\.[0-9] | tac | grep -v ${unavailable_versions} | awk -F. '{print $1"."$2}' | uniq)

latest_snapshot=$(echo ${tags} | head -c 5)

latest=""
for major_minor in ${major_minors} ; do
  max=0
  for tag in ${tags} ; do
    first=$(echo ${tag} | head -c 3)
    second=$(echo ${major_minor} | head -c 3)
    if [ ${first} = ${second} ] ; then
      micro=$(echo ${tag} | tail -c 2 | head -c 1)
      echo ${micro}
      if [ ${micro} -gt ${max} ] ; then
        max=${micro}
      fi
    fi
  done
  latest=$(echo -e "${major_minor}.${max}\n${latest}")
done

echo ${latest}

# Manualy add master there
latest=$(echo -e "master\n${latest}")

for tag in ${tags} ; do
  minor=$(echo ${tag} | head -c 3 | tail -c 1)
  if [ ${tag} != "master" ] && [ $((${minor} % 2)) -eq 0 ] ; then
    latest_release=${tag}
    break
  fi
done


for tag in ${latest} ; do
  # Everything needs to be in public/${version}/
  wget https://gitlab.com/BuildStream/buildstream/-/jobs/artifacts/${tag}/download?job=docs -O ${tag}.zip
  mkdir public/${tag}
  unzip ${tag}.zip -d public/${tag}
  mv public/${tag}/public/* public/${tag}
  minor=$(echo ${tag} | head -c 3 | tail -c 1)
  HTML_tag=$(echo "\n<li class=\"toctree-l1\"><a class=\"reference internal\" href=\"${tag}/index.html\">${tag}</a></li>")
  if [ ${tag} != "master" ] && [ $((${minor} % 2)) -eq 0 ] ; then
    stable_tags=$(echo "${stable_tags}\n${HTML_tag}")
  else
    snapshot_tags=$(echo "${snapshot_tags}\n${HTML_tag}")
  fi
done



# Truncate the leading \n
stable_tags=$(echo ${stable_tags} | tail -c +1)
snapshot_tags=$(echo ${snapshot_tags} | tail -c +1)

# Substitute the target line, creating the table of entries automatically.
sed -i "s#${stable_line}#${stable_tags}#g" public/index.html
sed -i "s#${snapshot_line}#${snapshot_tags}#g" public/index.html

# Substitute LATEST_RELEASE and LATEST_SNAPSHOT to update badges automatically.
sed -i "s#LATEST_SNAPSHOT#${latest_snapshot}#g" public/index.html
sed -i "s#LATEST_RELEASE#${latest_release}#g" public/index.html
