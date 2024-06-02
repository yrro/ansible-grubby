import importlib.util
from itertools import permutations
import json
from pathlib import Path
import sys

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes
import pytest


spec = importlib.util.spec_from_file_location("grubby", "library/grubby.py")
grubby = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grubby)


arg_test_params = [
    (grubby.FindArgResult.PRESENT, "foo", ["foo", "bar"]),
    (grubby.FindArgResult.CHANGED, "foo", ["foo=bar", "bar"]),
    (grubby.FindArgResult.CHANGED, "foo", ["xyz", "foo", "foo=baz"]),
    (grubby.FindArgResult.MISSING, "foo", ["bar", "qux"]),
    (grubby.FindArgResult.CHANGED, "foo", ["foo=bar", "foo=qux", "quux"]),
    (grubby.FindArgResult.PRESENT, "foo=bar", ["foo=bar", "baz"]),
    (grubby.FindArgResult.CHANGED, "foo=bar", ["foo=baz", "bar"]),
    (grubby.FindArgResult.CHANGED, "foo=bar", ["foo", "baz"]),
    (grubby.FindArgResult.MISSING, "foo=bar", ["baz=bar", "qux"]),
]

arg_test_params_permuted = []
for expected, arg, args in arg_test_params:
    for p in permutations(args):
        arg_test_params_permuted.append((expected, arg, p))

def permutate_id_fn(arg):
    if isinstance(arg, tuple):
        return ' '.join(list(arg))
    return None

@pytest.mark.parametrize("expected,arg,args", arg_test_params_permuted, ids=permutate_id_fn)
def test_find_arg_in(expected, arg, args):
    assert expected == grubby.find_arg_in(arg, args)


def set_module_args(args):
    args_json = json.dumps({"ANSIBLE_MODULE_ARGS": args})
    basic._ANSIBLE_ARGS = to_bytes(args_json)

class AnsibleExitJson(Exception):
    """Exception class to be raised by module.exit_json and caught by the test case"""
    pass

class AnsibleFailJson(Exception):
    """Exception class to be raised by module.fail_json and caught by the test case"""
    pass

def exit_json(*args, **kwargs):
    if "changed" not in kwargs:
        kwargs["changed"] = False
    raise AnsibleExitJson(kwargs)

def fail_json(*args, **kwargs):
    kwargs["failed"] = True
    raise AnsibleFailJson(kwargs)

def get_bin_path(self, arg, required=False):
    if Path(arg).name == "grubby":
        return "/mock/grubby"
    else:
        if required:
            fail_json(msg=f"{arg!r} not found")

def run_module(monkeypatch, args, grubby_info, grubby_update=(0, "", ""), want_grubby_args=False):
    monkeypatch.setattr(basic.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(basic.AnsibleModule, "fail_json", fail_json)
    monkeypatch.setattr(basic.AnsibleModule, "get_bin_path", get_bin_path)

    _grubby_info_args = []
    _grubby_update_args = []

    def run_command(self, args_, *args, **kwargs):
        assert args_[0] == "/mock/grubby"
        if args_[1].startswith("--info="):
            _grubby_info_args.extend(args_)
            return grubby_info
        elif args_[1].startswith("--update-kernel="):
            _grubby_update_args.extend(args_)
            return grubby_update
        else:
            assert False, f"{args_[0]}: unknown option {args_[1]}"

    monkeypatch.setattr(basic.AnsibleModule, "run_command", run_command)

    set_module_args(args)

    with pytest.raises(AnsibleExitJson) as excinfo:
        grubby.main()

    (result,) = excinfo.value.args
    if want_grubby_args:
        result["_grubby_info_args"] = _grubby_info_args
        result["_grubby_update_args"] = _grubby_update_args
    return result

grubby_state_single = """\
index=0
kernel=whatever
args="foo bar=baz"
root="something"
initrd="/boot/whatever"
title="blah"
id="..."
"""

def test_add_noval_noop_grubby_args(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["foo"], "kernel_path": "whatever"}, grubby_info=(0, grubby_state_single, ""), want_grubby_args=True)

    # then:
    assert ["/mock/grubby", "--info=whatever"] == result["_grubby_info_args"] and [] == result["_grubby_update_args"]

def test_add_noval_grubby_args(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["qux"], "kernel_path": "whatever"}, grubby_info=(0, grubby_state_single, ""), want_grubby_args=True)

    # then:
    assert ["/mock/grubby", "--info=whatever"] == result["_grubby_info_args"] and ["/mock/grubby", "--update-kernel=whatever", "--args=qux"] == result["_grubby_update_args"]

def test_remove_noval_noop_grubby_args(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["qux"], "kernel_path": "whatever"}, grubby_info=(0, grubby_state_single, ""), want_grubby_args=True)

    # then:
    assert ["/mock/grubby", "--info=whatever"] == result["_grubby_info_args"] and [] == result["_grubby_update_args"]

def test_remove_noval_grubby_args(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["foo"], "kernel_path": "whatever"}, grubby_info=(0, grubby_state_single, ""), want_grubby_args=True)

    # then:
    assert ["/mock/grubby", "--info=whatever"] == result["_grubby_info_args"] and ["/mock/grubby", "--update-kernel=whatever", "--remove-args=foo"] == result["_grubby_update_args"]

def test_add_noval_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["foo"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_add_noval(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["qux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": ["qux"], "args_removed": []} == result

def test_add_val_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["bar=baz"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_add_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["qux=quux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": ["qux=quux"], "args_removed": []} == result

def test_change_modify_val_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["bar=baz"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_change_modify_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["bar=qux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": ["bar=qux"], "args_removed": []} == result

def test_change_add_val_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["bar=baz"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_change_add_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["foo=qux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": ["foo=qux"], "args_removed": []} == result

def test_change_remove_val_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["foo"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_change_remove_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["bar"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": ["bar"], "args_removed": []} == result

def test_remove_val_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["qux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_remove_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["bar"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": [], "args_removed": ["bar"]} == result

def test_remove_noval_noop(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["qux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": False, "args_added": [], "args_removed": []} == result

def test_remove_noval(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["foo"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_single, ""))

    # then:
    assert {"changed": True, "args_added": [], "args_removed": ["foo"]} == result

grubby_state_multi = """\
index=0
kernel=whatever
args="foo bar=baz quux"
root="something"
initrd="/boot/whatever"
title="blah"
id="..."
index=1
kernel=whatever
args="foo bar=qux"
root="something"
initrd="/boot/whatever"
title="blah"
id="..."
"""

def test_multi_change_add_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["quux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_multi, ""))

    # then:
    assert {"changed": True, "args_added": ["quux"], "args_removed": []} == result

def test_multi_change_modify_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "present", "args": ["bar=quux"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_multi, ""))

    # then:
    assert {"changed": True, "args_added": ["bar=quux"], "args_removed": []} == result

def test_multi_change_remove_val(monkeypatch):
    # when:
    result = run_module(monkeypatch, args={"state": "absent", "args": ["bar=baz"], "_ansible_check_mode": True}, grubby_info=(0, grubby_state_multi, ""))

    # then:
    assert {"changed": True, "args_added": [], "args_removed": ["bar=baz"]} == result
