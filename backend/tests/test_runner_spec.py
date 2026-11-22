import pytest

from novacloud.runner.spec import build_run_args, container_name, validate_ref

ID = "123e4567-e89b-12d3-a456-426614174000"


def test_hardening_flags_present_and_no_privilege():
    a = build_run_args(ID, ID, "alpine-small")
    s = " ".join(a)
    assert "--cap-drop ALL" in s and "no-new-privileges" in s and "--read-only" in s
    assert "--network none" in s and "--memory 128m" in s and "--pids-limit" in s
    for forbidden in ("--privileged", "-v", "--volume", "--mount", "docker.sock", "--network host", "--pid", "--cap-add", "--device"):
        assert forbidden not in a and forbidden not in s.split()
    assert a[0] == "docker" and a[1] == "run"


@pytest.mark.parametrize("bad", ["ubuntu", "alpine-small; rm -rf /", "../x", ""])
def test_only_template_names_accepted(bad):
    with pytest.raises(ValueError):
        build_run_args(ID, ID, bad)


@pytest.mark.parametrize("bad", ["x; rm", "../../etc", "", "a" * 36])
def test_ids_validated(bad):
    with pytest.raises(ValueError):
        build_run_args(bad, ID, "alpine-small")
    with pytest.raises(ValueError):
        container_name(bad)


def test_ref_validation():
    assert validate_ref(container_name(ID)) == f"novacloud-{ID}"
    for bad in ["nginx", "novacloud-x", "-f novacloud-" + ID, "novacloud-" + ID + " --all"]:
        with pytest.raises(ValueError):
            validate_ref(bad)
