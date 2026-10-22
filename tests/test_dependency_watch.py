"""Offline binary release-watch contracts; no real network or issue writes."""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "dependency_watch", Path(__file__).parents[1] / "scripts/watch_dependency_releases.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)

REPO = "owner/ghostfolio-boursedirect-sync"
PINS = [
    {"ecosystem": "github", "name": "bitwarden/clients", "version": "2026.9.1", "tag_prefix": "cli-v"},
    {"ecosystem": "chrome", "name": "chrome-headless-shell", "version": "155.0.8059.39"},
]


def fake_api(issues=None, releases=None):
    api = SimpleNamespace(issues=list(issues or []), writes=[], reads=[])
    api.releases = releases if releases is not None else {
        "bitwarden/clients": [{"tag_name": "cli-v2026.9.2"}],
    }

    def list_all(path):
        api.reads.append(path)
        if path.endswith("/issues?state=all"):
            return api.issues
        if path.endswith("/labels"):
            return [{"name": "dependency-release"}]
        if path.endswith("/releases"):
            return api.releases[path.removeprefix("repos/").removesuffix("/releases")]
        raise AssertionError(path)

    def request(method, path, payload=None):
        assert method == "POST" and path.endswith("/issues"), path
        api.writes.append(payload)
        issue = {"number": len(api.issues) + 1, "body": payload["body"]}
        api.issues.append(issue)
        return issue

    api.list_all, api.request = list_all, request
    return api


def monitor(api, repository, pins, **kwargs):
    return watch.monitor(api, repository, pins, chrome_fetch=lambda: (
        [{"version": "155.0.8059.40"}], []), **kwargs)


@pytest.mark.parametrize("pin,new_version", [(PINS[0], "2026.9.2"), (PINS[1], "155.0.8059.40")])
def test_new_binary_opens_one_notice_and_closed_notice_is_not_duplicated(pin, new_version):
    api = fake_api()
    assert monitor(api, REPO, [pin]) == [1]
    assert api.writes[0]["title"] == f"Review {pin['name']} {new_version} (pinned {pin['version']})"
    assert api.writes[0]["labels"] == ["dependency-release"]
    assert watch.release_page(pin, new_version) in api.writes[0]["body"]
    assert "architecture-checksum update" in api.writes[0]["body"]
    api.issues[0]["state"] = "closed"
    assert monitor(api, REPO, [pin]) == []
    assert len(api.writes) == 1


@pytest.mark.parametrize("ecosystem,name", [("pypi", "requests"), ("npm", "apprise"),
                                          ("github", "owner/package")])
def test_package_updates_make_no_notices_or_metadata_reads(ecosystem, name):
    api = fake_api(releases={})
    assert monitor(api, REPO, [{"ecosystem": ecosystem, "name": name, "version": "1.0"}]) == []
    assert api.writes == [] and api.reads == []


def test_packages_do_not_block_binary_notices():
    api = fake_api()
    packages = [{"ecosystem": "pypi", "name": "requests", "version": "1.0"},
                {"ecosystem": "npm", "name": "example", "version": "1.0"}]
    assert monitor(api, REPO, packages + PINS) == [1, 2]
    assert [p["title"] for p in api.writes] == [
        "Review bitwarden/clients 2026.9.2 (pinned 2026.9.1)",
        "Review chrome-headless-shell 155.0.8059.40 (pinned 155.0.8059.39)"]


def test_major_minor_patch_are_flagged():
    pin = dict(PINS[0], version="0.2.49")
    assert "patch version change" in watch.notice_body(pin, {"version": "0.2.50"}, [])
    assert "minor version change" in watch.notice_body(pin, {"version": "0.3.0"}, [])
    assert "major version change: breaking changes are likely" in watch.notice_body(pin, {"version": "1.0"}, [])
    assert "patch version change" in watch.notice_body(dict(pin, version="2.0"), {"version": "2.0.1"}, [])


def test_equivalent_versions_get_one_notice_and_marker_matches_other_spelling():
    pin = dict(PINS[0], version="2.34.2")
    api = fake_api(releases={pin["name"]: [{"tag_name": "cli-v" + v} for v in
                                         ["2.34.2", "2.34.2.0", "2.35", "2.35.0"]]})
    assert monitor(api, REPO, [pin]) == [1]
    api.issues[0]["body"] = watch.release_marker(pin, "2.35")
    assert monitor(api, REPO, [pin]) == []


def test_markers_are_scoped_to_component_and_pr_markers_are_ignored():
    api = fake_api(issues=[{"body": watch.release_marker(PINS[1], "2026.9.2")},
                          {"body": watch.release_marker(PINS[0], "2026.9.2"), "pull_request": {}}])
    assert len(monitor(api, REPO, PINS[:1])) == 1


@pytest.mark.parametrize("pin", PINS[:1])
def test_release_prefix_excludes_other_clients_drafts_prereleases_and_unstable_versions(pin):
    prefix = pin.get("tag_prefix", "v")
    api = fake_api(releases={pin["name"]: [
        {"tag_name": prefix + "9999.0"}, {"tag_name": prefix + "9999.1", "draft": True},
        {"tag_name": prefix + "9999.2", "prerelease": True},
        {"tag_name": prefix + "9999.3rc1"}, {"tag_name": "web-v9999.0"}, {"tag_name": "nightly"}]})
    assert len(monitor(api, REPO, [pin])) == 1
    assert "9999.0" in api.writes[0]["title"]


def test_untrusted_timestamp_is_not_copied_as_markup():
    api = fake_api(releases={PINS[0]["name"]: [
        {"tag_name": "cli-v2026.9.2", "published_at": "@everyone [x](https://evil.invalid)"}]})
    monitor(api, REPO, PINS[:1])
    body = api.writes[0]["body"]
    assert "evil.invalid" not in body and "@everyone" not in body
    assert "Published: unknown" in body


def test_new_issues_are_capped_and_remaining_releases_follow_next_run():
    pin = dict(PINS[0], version="1.0")
    api = fake_api(releases={pin["name"]: [{"tag_name": f"cli-v1.{i}"} for i in range(15)]})
    assert len(monitor(api, REPO, [pin])) == watch.MAX_NEW_ISSUES_PER_RUN
    assert len(monitor(api, REPO, [pin])) == 4


def test_nothing_new_makes_no_issue_or_label_call():
    api = fake_api(releases={PINS[0]["name"]: [{"tag_name": "cli-v2026.9.1"}]})
    assert monitor(api, REPO, PINS[:1]) == []
    assert api.writes == []
    assert api.reads == ["repos/bitwarden/clients/releases"]


def test_fetch_failure_stops_before_any_write():
    api = fake_api(releases={PINS[0]["name"]: [{"tag_name": "cli-v2026.9.2"}]})
    listing = api.list_all

    def broken(path):
        if "issues?" in path:
            raise RuntimeError("Synthetic upstream failure")
        return listing(path)

    api.list_all = broken
    with pytest.raises(RuntimeError, match="Synthetic upstream failure"):
        monitor(api, REPO, PINS)
    assert api.writes == []


def test_invalid_destination_repository_is_rejected():
    with pytest.raises(RuntimeError):
        monitor(fake_api(), "not a repo", PINS)


def dockerfile_pins(bitwarden="2026.9.1", chrome="155.0.8059.39"):
    return ("FROM node:22\n"
            f"https://github.com/bitwarden/clients/releases/download/cli-v{bitwarden}/bw-linux-{bitwarden}.zip\n"
            f"https://storage.googleapis.com/chrome-for-testing-public/{chrome}/linux64/chrome-headless-shell-linux64.zip\n")


def test_only_binary_pins_are_read_without_package_manifests(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(dockerfile_pins())
    before = dockerfile.read_bytes()
    assert watch.read_pins(tmp_path) == PINS
    (tmp_path / "requirements.txt").write_text("requests>=999\n")
    (tmp_path / "package.json").write_text('{"dependencies":{"example":"99999.0"}}')
    assert watch.read_pins(tmp_path) == PINS
    assert monitor(fake_api(), REPO, watch.read_pins(tmp_path)) == [1, 2]
    assert dockerfile.read_bytes() == before


@pytest.mark.parametrize("dockerfile", [
    "FROM node\n", dockerfile_pins(bitwarden="2026.9.2rc1"),
    dockerfile_pins(chrome="155.0.8059.40rc1"),
    dockerfile_pins() + dockerfile_pins(bitwarden="2026.9.2"),
    dockerfile_pins() + dockerfile_pins(chrome="155.0.8059.40"),
])
def test_missing_unstable_or_ambiguous_binary_pins_fail_loudly(tmp_path, dockerfile):
    (tmp_path / "Dockerfile").write_text(dockerfile)
    with pytest.raises(RuntimeError):
        watch.read_pins(tmp_path)


def chrome_entry(version, platform="linux64", binary="chrome-headless-shell"):
    return {"version": version, "downloads": {binary: [{"platform": platform,
        "url": f"https://storage.googleapis.com/chrome-for-testing-public/{version}/{platform}/{binary}-{platform}.zip"}]}}


def catalog_opener(monkeypatch, raw):
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        assert timeout == 30
        return io.BytesIO(raw)

    def build(*handlers):
        assert handlers[0].proxies == {}
        assert handlers[1].redirect_request(None, None, None, None, None, None) is None
        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(watch, "build_opener", build)
    return requests


def test_chrome_catalog_filters_binary_platform_and_untrusted_downloads(monkeypatch):
    wrong_url = chrome_entry("155.0.8059.43")
    wrong_url["downloads"]["chrome-headless-shell"][0]["url"] = "https://evil.invalid/file.zip"
    raw = json.dumps({"versions": [chrome_entry("155.0.8059.40"),
        chrome_entry("155.0.8059.41", platform="win64"),
        chrome_entry("155.0.8059.42", binary="chrome"), wrong_url]}).encode()
    requests = catalog_opener(monkeypatch, raw)
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-secret")
    assert watch.chrome_releases() == ([{"version": "155.0.8059.40"}], [])
    assert requests[0].full_url == watch.CHROME_CATALOG
    assert requests[0].get_header("Authorization") is None


@pytest.mark.parametrize("raw", [b"invalid", b"{}", b'{"versions": []}',
    b'{"versions": null}', b'{"versions": [{"version": "bad"}]}'])
def test_invalid_chrome_catalog_fails_before_issue_writes(monkeypatch, raw):
    catalog_opener(monkeypatch, raw)
    api = fake_api()
    with pytest.raises(RuntimeError, match="Chrome catalog request failed"):
        watch.monitor(api, REPO, PINS)
    assert api.writes == []


def test_chrome_catalog_size_is_bounded(monkeypatch):
    monkeypatch.setattr(watch, "MAX_CATALOG_BYTES", 10)
    catalog_opener(monkeypatch, b"x" * 11)
    with pytest.raises(RuntimeError, match="size limit"):
        watch.chrome_releases()


def test_chrome_request_failure_stops_before_any_write(monkeypatch):
    def broken(*args, **kwargs):
        raise watch.URLError("synthetic upstream failure")

    monkeypatch.setattr(watch, "build_opener", lambda *handlers: SimpleNamespace(open=broken))
    api = fake_api()
    with pytest.raises(RuntimeError, match="Chrome catalog request failed"):
        watch.monitor(api, REPO, PINS)
    assert api.writes == []


def test_main_reads_fixture_pins_and_uses_simulated_upstreams(monkeypatch, capsys, tmp_path):
    api = fake_api()
    # The package image no longer ships broker or vault binaries. Keep the
    # legacy watcher's offline behavior covered until task 1.3 removes it.
    (tmp_path / "Dockerfile").write_text(dockerfile_pins())
    pins = watch.read_pins(tmp_path)
    monkeypatch.setattr(watch, "read_pins", lambda: pins)
    bw = next(pin for pin in pins if pin["ecosystem"] == "github")
    chrome = next(pin for pin in pins if pin["ecosystem"] == "chrome")
    bw_next = bw["version"] + ".1"
    chrome_next = chrome["version"] + ".1"
    api.releases = {bw["name"]: [{"tag_name": "cli-v" + bw_next}]}
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setattr(watch, "github_api", lambda: api)
    monkeypatch.setattr(watch, "chrome_releases", lambda: ([{"version": chrome_next}], []))
    watch.main()
    assert len(api.writes) == 2
    watch.main()
    assert len(api.writes) == 2
    assert "Every new dependency release already has a review issue" in capsys.readouterr().out
