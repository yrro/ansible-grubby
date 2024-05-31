import importlib.util
import json
from pathlib import Path
import sys

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes
import pytest

spec = importlib.util.spec_from_file_location("grubby", "library/grubby.py")
grubby = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grubby)


def test_simple_arg_present():
    assert grubby.FindArgResult.PRESENT == grubby.find_arg_in("foo", ["foo", "bar"])

def test_simple_arg_value_present():
    assert grubby.FindArgResult.CHANGED == grubby.find_arg_in("foo", ["foo=baz", "bar"])

def test_simple_arg_absent():
    assert grubby.FindArgResult.MISSING == grubby.find_arg_in("qux", ["foo", "bar"])

def test_complex_arg_value_present_matching():
    assert grubby.FindArgResult.PRESENT == grubby.find_arg_in("foo=bar", ["foo=bar", "baz"])

def test_complex_arg_value_present_different():
    assert grubby.FindArgResult.CHANGED == grubby.find_arg_in("foo=bar", ["foo=baz", "bar"])

def test_complex_arg_value_present_missing():
    assert grubby.FindArgResult.CHANGED == grubby.find_arg_in("foo=bar", ["foo", "baz"]) 

def test_complex_arg_value_absent():
    assert grubby.FindArgResult.MISSING == grubby.find_arg_in("foo=bar", ["baz=bar"])


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

def run_module(monkeypatch, args, grubby_info):
    monkeypatch.setattr(basic.AnsibleModule, "exit_json", exit_json)
    monkeypatch.setattr(basic.AnsibleModule, "fail_json", fail_json)
    monkeypatch.setattr(basic.AnsibleModule, "get_bin_path", get_bin_path)

    def run_command(self, args_, *args, **kwargs):
        assert args_[0] == "/mock/grubby"
        return grubby_info

    monkeypatch.setattr(basic.AnsibleModule, "run_command", run_command)

    set_module_args(args)

    with pytest.raises(AnsibleExitJson) as excinfo:
        grubby.main()

    (result,) = excinfo.value.args
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
