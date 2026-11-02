#!/bin/bash
# Installs the requirements file $2 with the Python $1, as Home Assistant would have them: on a
# development branch $3 with the libraries' branch of the same name in place of their pins, under
# Home Assistant's package constraints, and with Home Assistant's version of each package the
# integration requires that its own integrations pin. Run from the repository's root; $4 is the
# owner of the libraries.
set -eo pipefail

python=$1
requirements=$2
branch=$3
owner=$4
here=$(dirname "${BASH_SOURCE[0]}")
common="$here/../../../common/tools"
tools="$here/../../tools"

if [[ -n "$branch" && "$branch" != "main" ]]; then
  "$python" "$common/libraries.py" branch . "$owner" "$branch" > "$requirements.libraries"
  mapfile -t libraries < "$requirements.libraries"
  if (( ${#libraries[@]} )); then
    printf 'Library from branch %s: %s\n' "$branch" "${libraries[@]}"
    "$python" "$common/libraries.py" requirements "$requirements" "${libraries[@]}"
  fi
fi
"$python" -m pip install -r "$requirements"
# Home Assistant installs an integration's requirements under its package constraints, so the
# tests do too: a package outside them, such as cffi, is replaced at Home Assistant's version as
# Home Assistant would have it.
constraints=$("$python" -c 'import homeassistant, pathlib; print(pathlib.Path(homeassistant.__file__).parent / "package_constraints.txt")')
"$python" -m pip install -r "$requirements" -c "$constraints"
# A package Home Assistant's own integrations pin is at their version wherever one of them is
# set up; it follows the Home Assistant installed rather than a line kept by hand.
"$python" "$tools/contract.py" pins . > "$requirements.pins"
mapfile -t pins < "$requirements.pins"
if (( ${#pins[@]} )); then
  printf "Home Assistant's version: %s\n" "${pins[@]}"
  "$python" -m pip install "${pins[@]}" -c "$constraints"
fi
