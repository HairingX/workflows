"""Tests of how a release and a test build work out their version."""

import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from packaging.version import Version
from release_version import (
    FINAL_RELEASE,
    RELEASE_CANDIDATE,
    known_versions,
    main,
    newest_draft,
    next_version,
    final_notes,
    previous_tag,
    require_changes,
    next_release_base,
    next_test_build,
    write,
)

AULA_MANIFEST = """{
    "domain": "aula",
    "name": "Aula",
    "requirements": [
        "lxml>=5.0.0"
    ],
    "version": "0.0.0"
}"""


def _next(kind: str, draft: str, known: list[str], override: str = "") -> str:
    return str(next_version(kind, draft, override, known_versions(known))[0])


def _uses_draft(kind: str, draft: str, known: list[str], override: str = "") -> bool:
    return next_version(kind, draft, override, known_versions(known))[2]


class TestNextVersion(unittest.TestCase):
    def test_a_release_candidate_continues_the_open_series_below_the_draft(
        self,
    ) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.1.10", ["v0.1.8", "0.1.9", "v0.2.0rc1"]),
            "0.2.0rc2",
        )

    def test_a_final_release_ends_the_open_series(self) -> None:
        self.assertEqual(
            _next(FINAL_RELEASE, "v0.1.10", ["v0.1.8", "v0.2.0rc1", "v0.2.0rc2"]),
            "0.2.0",
        )

    def test_a_draft_above_the_open_series_starts_a_new_one(self) -> None:
        self.assertEqual(_next(RELEASE_CANDIDATE, "v0.3.0", ["v0.2.0rc2"]), "0.3.0rc1")
        self.assertEqual(_next(FINAL_RELEASE, "v0.3.0", ["v0.2.0rc2"]), "0.3.0")

    def test_a_draft_naming_the_open_series_continues_it(self) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.2.0", ["v0.1.0", "v0.2.0rc1"]), "0.2.0rc2"
        )

    def test_a_new_major_version_is_never_worked_out(self) -> None:
        for kind in (RELEASE_CANDIDATE, FINAL_RELEASE):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                SystemExit, r"1\.0\.0(rc1)? is a new major version"
            ):
                _next(kind, "v1.0.0", ["v0.2.0rc2"])

    def test_a_new_major_version_is_taken_as_an_override(self) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.2.1", ["v0.2.0"], override="1.0.0rc1"),
            "1.0.0rc1",
        )

    def test_without_an_open_series_the_draft_names_the_version(self) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.3.0", ["v0.2.0rc1", "v0.2.0"]), "0.3.0rc1"
        )
        self.assertEqual(_next(FINAL_RELEASE, "v0.3.0", ["v0.2.0"]), "0.3.0")

    def test_the_first_release_needs_nothing_known(self) -> None:
        self.assertEqual(_next(FINAL_RELEASE, "v0.1.0", []), "0.1.0")

    def test_an_open_series_needs_no_draft(self) -> None:
        self.assertEqual(_next(RELEASE_CANDIDATE, "", ["v0.2.0rc1"]), "0.2.0rc2")
        self.assertEqual(_next(FINAL_RELEASE, "", ["v0.2.0rc1"]), "0.2.0")

    def test_without_a_draft_or_an_open_series_the_version_must_be_given(self) -> None:
        with self.assertRaisesRegex(SystemExit, "give the version as the override"):
            _next(FINAL_RELEASE, "", ["v0.2.0"])

    def test_a_draft_below_what_is_published_is_refused(self) -> None:
        with self.assertRaisesRegex(SystemExit, r"0\.1\.10 is not higher than 0\.2\.0"):
            _next(FINAL_RELEASE, "v0.1.10", ["v0.2.0"])

    def test_a_draft_naming_a_pre_release_is_refused(self) -> None:
        with self.assertRaisesRegex(SystemExit, "a pre-release, not the next version"):
            _next(FINAL_RELEASE, "v0.3.0rc1", ["v0.2.0"])

    def test_the_override_replaces_the_version_worked_out(self) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.1.10", ["v0.2.0rc1"], override="0.3.0rc1"),
            "0.3.0rc1",
        )

    def test_the_override_must_still_be_higher_than_every_known_version(self) -> None:
        with self.assertRaisesRegex(
            SystemExit, r"0\.2\.0rc1 is not higher than 0\.2\.0rc1"
        ):
            _next(RELEASE_CANDIDATE, "", ["v0.2.0rc1"], override="0.2.0rc1")
        with self.assertRaisesRegex(SystemExit, r"0\.1\.11 is not higher than 0\.2\.8"):
            _next(FINAL_RELEASE, "v0.2.9", ["v0.2.8"], override="0.1.11")

    def test_the_override_must_be_the_kind_chosen(self) -> None:
        for kind, override in (
            (FINAL_RELEASE, "0.2.0rc2"),
            (RELEASE_CANDIDATE, "0.2.0"),
        ):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                SystemExit, f"not a {kind}"
            ):
                _next(kind, "", ["v0.2.0rc1"], override=override)

    def test_the_override_of_a_release_candidate_must_be_a_release_candidate(
        self,
    ) -> None:
        with self.assertRaisesRegex(SystemExit, "is not a release candidate"):
            _next(RELEASE_CANDIDATE, "", ["v0.2.0"], override="0.3.0b1")

    def test_the_override_must_be_canonical_major_minor_patch(self) -> None:
        for override in ("v0.3.0", "0.3", "0.3.0-rc1", "0.3.0+local", "0.3.0-dev.1"):
            with self.subTest(override=override), self.assertRaisesRegex(
                SystemExit, "::error::"
            ):
                _next(FINAL_RELEASE, "", [], override=override)

    def test_a_development_or_post_release_is_refused(self) -> None:
        for kind, override in (
            (RELEASE_CANDIDATE, "1.0.0.dev1"),
            (RELEASE_CANDIDATE, "1.0.0rc1.post1"),
            (FINAL_RELEASE, "0.3.0.post1"),
        ):
            with self.subTest(override=override), self.assertRaisesRegex(
                SystemExit, "must be MAJOR.MINOR.PATCH"
            ):
                _next(kind, "", ["v0.2.8"], override=override)

    def test_an_unknown_kind_is_refused(self) -> None:
        with self.assertRaisesRegex(SystemExit, "neither"):
            _next("final", "v0.1.0", [])

    def test_this_repositorys_tags_and_draft_give_the_next_patch(self) -> None:
        tags = [f"v0.1.{n}" for n in range(11)] + [f"v0.2.{n}" for n in range(9)]
        self.assertEqual(_next(FINAL_RELEASE, "v0.2.9", tags), "0.2.9")
        self.assertEqual(_next(RELEASE_CANDIDATE, "v0.2.9", tags), "0.2.9rc1")


class TestTestBuildTags(unittest.TestCase):
    def test_a_test_build_does_not_open_a_series(self) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.2.9", ["v0.2.8", "v0.3.0b1"]), "0.2.9rc1"
        )
        self.assertEqual(
            _next(FINAL_RELEASE, "v0.2.9", ["v0.2.8", "v0.3.0b1"]), "0.2.9"
        )

    def test_a_test_build_does_not_bound_the_next_release(self) -> None:
        self.assertEqual(
            _next(FINAL_RELEASE, "", ["v0.2.8", "v0.3.0b2"], override="0.2.9"), "0.2.9"
        )

    def test_a_series_of_release_candidates_ignores_test_builds_after_it(self) -> None:
        self.assertEqual(
            _next(RELEASE_CANDIDATE, "v0.3.0", ["v0.3.0rc1", "v0.3.0b4"]), "0.3.0rc2"
        )

    def test_a_major_version_tag_names_no_release(self) -> None:
        self.assertEqual(known_versions(["v1", "v1.2", "v1.0.0"]), [Version("1.0.0")])

    def test_tags_that_name_no_release_are_skipped(self) -> None:
        self.assertEqual(
            known_versions(
                [
                    "v0.1.0",
                    "latest",
                    "",
                    "0.2.0rc1",
                    "v0.2.0b1",
                    "v0.2.0.dev1",
                    "v0.1.1\r",
                ]
            ),
            [Version("0.1.0"), Version("0.2.0rc1"), Version("0.1.1")],
        )


class TestUsesDraft(unittest.TestCase):
    def test_a_final_release_uses_the_draft_for_its_notes(self) -> None:
        self.assertTrue(_uses_draft(FINAL_RELEASE, "v0.3.0", ["v0.2.0"]))
        self.assertTrue(_uses_draft(FINAL_RELEASE, "v0.2.0", ["v0.2.0rc1"]))
        self.assertTrue(
            _uses_draft(FINAL_RELEASE, "v0.2.9", ["v0.2.8"], override="0.3.0")
        )

    def test_a_final_release_without_a_draft_does_not(self) -> None:
        self.assertFalse(_uses_draft(FINAL_RELEASE, "", ["v0.2.0rc1"]))

    def test_a_release_candidate_uses_the_draft_only_for_its_version(self) -> None:
        self.assertTrue(_uses_draft(RELEASE_CANDIDATE, "v0.3.0", ["v0.2.0"]))
        self.assertFalse(_uses_draft(RELEASE_CANDIDATE, "v0.2.0", ["v0.2.0rc1"]))
        self.assertFalse(
            _uses_draft(RELEASE_CANDIDATE, "v0.3.0", ["v0.2.0"], override="0.4.0rc1")
        )


class TestTestBuildVersion(unittest.TestCase):
    def test_a_test_build_is_numbered_by_its_run(self) -> None:
        self.assertEqual(next_test_build("0.2.9", ["v0.2.8"], 57), Version("0.2.9b57"))

    def test_a_test_build_is_higher_than_every_one_before_it(self) -> None:
        tags = ["v0.2.9b1", "v0.2.9b60", "v0.3.0b2", "v0.2.9rc1"]
        self.assertEqual(next_test_build("0.2.9", tags, 57), Version("0.2.9b61"))
        self.assertEqual(next_test_build("0.3.0", tags, 57), Version("0.3.0b57"))

    def test_a_new_test_build_is_never_numbered_as_one_it_replaced(self) -> None:
        first = next_test_build("0.0.12", ["v0.0.11"], 7)
        second = next_test_build("0.0.12", ["v0.0.11"], 8)
        self.assertGreater(second, first)

    def test_the_base_must_be_a_final_version(self) -> None:
        for base in ("0.2.9rc1", "0.2", "v0.2.9"):
            with self.subTest(base=base), self.assertRaisesRegex(
                SystemExit, "::error::"
            ):
                next_test_build(base, [], 1)


class TestNextReleaseBase(unittest.TestCase):
    def test_the_draft_names_the_next_release(self) -> None:
        self.assertEqual(next_release_base("v0.3.0", [Version("0.2.8")]), "0.3.0")

    def test_without_a_draft_the_patch_after_the_last_final_release(self) -> None:
        known = [Version("0.2.8"), Version("0.3.0rc1"), Version("0.2.10")]
        self.assertEqual(next_release_base("", known), "0.2.11")

    def test_without_a_draft_or_a_final_release_there_is_none(self) -> None:
        with self.assertRaisesRegex(SystemExit, "no final release"):
            next_release_base("", [Version("0.1.0rc1")])


class TestPreviousTag(unittest.TestCase):
    def test_the_notes_of_a_release_candidate_start_at_the_one_before(self) -> None:
        self.assertEqual(
            previous_tag(Version("0.2.0rc2"), ["v0.1.9", "v0.2.0rc1", "v0.2.0rc2"]),
            "v0.2.0rc1",
        )

    def test_the_notes_of_a_final_release_start_at_the_final_release_before(
        self,
    ) -> None:
        self.assertEqual(
            previous_tag(Version("0.2.0"), ["v0.1.9", "v0.2.0rc1", "v0.2.0rc2"]),
            "v0.1.9",
        )

    def test_the_notes_of_a_new_series_start_at_the_final_release_before(self) -> None:
        self.assertEqual(
            previous_tag(Version("0.3.0rc1"), ["v0.2.0rc2", "v0.2.0", "latest"]),
            "v0.2.0",
        )

    def test_the_notes_skip_test_builds(self) -> None:
        self.assertEqual(
            previous_tag(Version("0.2.0rc1"), ["v0.1.0", "v0.2.0b3", "v0.1.5.dev1"]),
            "v0.1.0",
        )

    def test_the_first_release_notes_start_from_the_beginning(self) -> None:
        self.assertIsNone(previous_tag(Version("0.1.0"), []))
        self.assertIsNone(previous_tag(Version("0.2.0"), ["v0.2.0rc1", "v0.2.0rc2"]))


class TestChanges(unittest.TestCase):
    def test_a_release_without_a_merged_pull_request_is_refused(self) -> None:
        with self.assertRaisesRegex(
            SystemExit, "no pull request has been merged since v0.3.0"
        ):
            require_changes("v0.3.0", ["", "  "])

    def test_a_release_with_a_merged_pull_request_goes_ahead(self) -> None:
        require_changes("v0.3.0", ["10"])


class TestDraft(unittest.TestCase):
    def test_the_newest_draft_is_picked_across_pages(self) -> None:
        lines = [
            json.dumps(
                {
                    "id": 9,
                    "draft": True,
                    "tag_name": "v0.2.8",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ),
            json.dumps(
                {
                    "id": 2,
                    "draft": False,
                    "tag_name": "v0.2.9",
                    "created_at": "2026-09-01T00:00:00Z",
                }
            ),
            "",
            json.dumps(
                {
                    "id": 3,
                    "draft": True,
                    "tag_name": "v0.2.9",
                    "created_at": "2026-08-01T00:00:00Z",
                }
            ),
        ]
        found = newest_draft(lines)
        assert found is not None
        self.assertEqual(found["id"], 3)

    def test_a_body_with_a_unicode_line_separator_is_read(self) -> None:
        body = "- #15 Title with \u2028 and \u0085 inside"
        release = {
            "id": 7,
            "draft": True,
            "tag_name": "v0.2.9",
            "created_at": "x",
            "body": body,
        }
        with tempfile.TemporaryDirectory() as directory:
            drafts = Path(directory) / "drafts"
            drafts.write_text(
                json.dumps(release, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            output = _run(["draft", str(drafts)])
        encoded = output.splitlines()[2].removeprefix("draft_body=")
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), body)

    def test_without_a_draft_there_is_none(self) -> None:
        self.assertIsNone(newest_draft([]))

    def test_the_draft_is_printed_with_its_body_in_base64(self) -> None:
        body = "## Changes\r\n- #12 Fix æøå @HairingX\n"
        release = {
            "id": 7,
            "draft": True,
            "tag_name": "v0.2.9",
            "created_at": "x",
            "body": body,
        }
        with tempfile.TemporaryDirectory() as directory:
            drafts = Path(directory) / "drafts"
            drafts.write_text(json.dumps(release) + "\n", encoding="utf-8")
            output = _run(["draft", str(drafts)])
        lines = dict(line.split("=", 1) for line in output.splitlines())
        self.assertEqual(lines["draft_id"], "7")
        self.assertEqual(lines["draft_tag"], "v0.2.9")
        self.assertEqual(base64.b64decode(lines["draft_body"]).decode("utf-8"), body)

    def test_without_a_draft_empty_values_are_printed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            drafts = Path(directory) / "drafts"
            drafts.write_text("", encoding="utf-8")
            output = _run(["draft", str(drafts)])
        self.assertEqual(output, "draft_id=\ndraft_tag=\ndraft_body=\n")


class TestWrite(unittest.TestCase):
    def test_only_the_version_line_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(AULA_MANIFEST, encoding="utf-8")
            write("0.2.9rc1", manifest)
            self.assertEqual(
                manifest.read_text(encoding="utf-8"),
                AULA_MANIFEST.replace('"version": "0.0.0"', '"version": "0.2.9rc1"'),
            )

    def test_a_manifest_without_exactly_one_version_line_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text('{"domain": "aula"}', encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "found 0"):
                write("0.2.9", manifest)



class TestFinalNotes(unittest.TestCase):
    def test_a_final_release_carries_the_drafts_notes(self) -> None:
        self.assertEqual(final_notes("v0.2.8", "## Fixes\n* A fix\n"), "## Fixes\n* A fix\n")

    def test_the_first_final_release_says_it_is_the_initial_release(self) -> None:
        self.assertEqual(final_notes("", "> [!WARNING]\n> no baseline\n"), "Initial release.\n")


class TestCommandLine(unittest.TestCase):
    def test_next_prints_what_the_workflow_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tags = Path(directory) / "tags"
            tags.write_text("v0.2.7\nv0.2.8\nv0.3.0b1\n", encoding="utf-8")
            output = _run(["next", FINAL_RELEASE, "v0.2.9", "", str(tags)])
        self.assertEqual(
            output,
            "version=0.2.9\ntag=v0.2.9\nprerelease=false\nprevious_tag=v0.2.8\nuses_draft=true\n",
        )

    def test_final_notes_writes_the_notes_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            notes = Path(directory) / "notes.md"
            body = base64.b64encode("## Fixes\n* Ræv\n".encode()).decode()
            _run(["final-notes", "v0.2.8", body, str(notes)])
            self.assertEqual(notes.read_text(encoding="utf-8"), "## Fixes\n* Ræv\n")
            _run(["final-notes", "", body, str(notes)])
            self.assertEqual(notes.read_text(encoding="utf-8"), "Initial release.\n")

    def test_a_version_the_package_index_has_taken_is_never_released_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tags = Path(directory) / "tags"
            tags.write_text("v0.2.8\n", encoding="utf-8")
            published = Path(directory) / "published"
            published.write_text("0.2.8\n0.2.9\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                _run(["next", FINAL_RELEASE, "v0.2.9", "", str(tags), str(published)])
            output = _run(["next", FINAL_RELEASE, "v0.3.0", "", str(tags), str(published)])
        self.assertIn("version=0.3.0\n", output)
        self.assertIn("previous_tag=v0.2.8\n", output)

    def test_test_build_prints_what_the_workflow_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tags = Path(directory) / "tags"
            tags.write_text("v0.2.8\nv0.2.9b1\n", encoding="utf-8")
            output = _run(["test-build", "0.2.9", str(tags), "57"])
        self.assertEqual(output, "version=0.2.9b57\ntag=v0.2.9b57\nprerelease=true\n")

    def test_a_test_build_without_a_draft_takes_the_next_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tags = Path(directory) / "tags"
            tags.write_text("v0.2.8\nv0.2.9b1\nv0.3.0b1\n", encoding="utf-8")
            output = _run(["test-build", "", str(tags), "1"])
        self.assertEqual(output, "version=0.2.9b2\ntag=v0.2.9b2\nprerelease=true\n")


def _run(arguments: list[str]) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        main(arguments)
    return out.getvalue()


if __name__ == "__main__":
    unittest.main()
