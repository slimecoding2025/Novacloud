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


def test_network_args_are_internal_private_and_validated():
    from novacloud.runner.spec import build_network_args, network_name, validate_net_ref
    a = build_network_args(ID, "10.0.1.0/24", "10.0.1.1")
    assert "--internal" in a and a[-1] == f"novacloud-net-{ID}" and "--subnet" in a
    assert validate_net_ref(network_name(ID)) == f"novacloud-net-{ID}"
    for cidr, gw in [("8.8.8.0/24", "8.8.8.1"), ("10.0.1.0/24", "10.9.9.9"), ("10.0.1.1/24", "10.0.1.1"), ("fd00::/64", "fd00::1"), ("10.0.0.0/30", "10.0.0.1")]:
        with pytest.raises(ValueError):
            build_network_args(ID, cidr, gw)
    for bad in ["bridge", "host", "novacloud-net-x", "novacloud-net-" + ID + " --force"]:
        with pytest.raises(ValueError):
            validate_net_ref(bad)


def test_attached_container_uses_user_network_and_ip_only():
    s = build_run_args(ID, ID, "alpine-small", network=ID, ip="10.0.1.5")
    j = " ".join(s)
    assert f"--network novacloud-net-{ID}" in j and "--ip 10.0.1.5" in j and "--network none" not in j
    assert "--network host" not in j and "--privileged" not in s
    for bad_ip in ["", "10.0.1.5; rm -rf /", "::1", "999.1.1.1"]:
        with pytest.raises(ValueError):
            build_run_args(ID, ID, "alpine-small", network=ID, ip=bad_ip)
    with pytest.raises(ValueError):
        build_run_args(ID, ID, "alpine-small", network="host", ip="10.0.1.5")
