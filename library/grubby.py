#!/usr/bin/python

# Copyright: (c) 2024, Sam Morris <sam@robots.org.uk>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)

import enum

from ansible.module_utils.basic import AnsibleModule


__metaclass__ = type

DOCUMENTATION = r'''
---
module: grubby

short_description: manipulate kernel parameters with grubby

version_added: "1.0.0"

description: XXX This is my longer description explaining my test module.

options:
    args:
        description: Arguments to manipulate
        required: true
        type: str | list | dict
    kernel_path:
        description: ALL, DEFAULT, or path to kernel image
        required: false
        type: str
    state:
        description:
            - Control to demo if the result of this module is changed or not.
            - Parameter description can be a list as well.
        required: true
        type: str
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
# extends_documentation_fragment:
#     - my_namespace.my_collection.my_doc_fragment_name XXX

author:
    - Sam Morris @yrro
'''

EXAMPLES = r'''
# Add kernel parameters to all kernels
- name: Ensure kernel parameters are present
  grubby:
    args: foo=bar baz=qux
    state: present

# Add several kernel parameters to all kernels
- name: Ensure kernel parameters are present
  grubby:
    args:
    - foo=bar
    - baz=qux
    state: present

# Add parameters to the default kernel only, using a dict
- name: Ensure kernel parameters are present for default kernel
  grubby:
    args:
      foo: bar
      baz: qux
    kernel_path: DEFAULT
    state: present

# Remove kernel parameters from all kernels
- name: Ensure kernel parameters are absent
  grubby:
    args:
    - foo
    - baz
    state: absent
'''

RETURN = r'''
#  XXX These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: The original name param that was passed in.
    type: str
    returned: always
    sample: 'hello world'
message:
    description: The output message that the test module generates.
    type: str
    returned: always
    sample: 'goodbye'
'''


def main():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        args=dict(type='list', required=True),
        state=dict(type='str', required=True, choices=['present', 'absent']),
        kernel_path=dict(type='str', default='ALL'),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        args_added=[],
        args_removed=[],
    )

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

    grubby_bin_path = module.get_bin_path("grubby")

    grubby_args = [grubby_bin_path, "--info="+module.params["kernel_path"]]
    rc, stdout, stderr = module.run_command([grubby_bin_path, "--info="+module.params["kernel_path"]])
    if rc != 0:
        module.fail_json("grubby failed", args=grubby_args, rc=rc, stdout=stdout, stderr=stderr)

    all_current_args = []
    for line in stdout.split("\n"):
        if not line.startswith('args="'):
            continue
        if not line.endswith('"'):
            module.fail_json(r'grubby output did not end with "', line=line)
        all_current_args.append(line[6:-1].split(" "))

    if len(all_current_args) == 0:
        module.fail_json("grubby returned no current args for kernel_path", kernel_path=kernel_path)

    args_to_change = set()

    for current_args in all_current_args:
        for arg in module.params["args"]:
            far = find_arg_in(arg, current_args)
            if module.params['state'] == 'present':
                if far in [FindArgResult.MISSING, FindArgResult.CHANGED]:
                    args_to_change.add(arg)
            elif module.params['state'] == 'absent':
                if far in [FindArgResult.PRESENT, FindArgResult.CHANGED]:
                    args_to_change.add(arg)

    if module.check_mode or not args_to_change:
        module.exit_json(**result)

    grubby_args = [grubby_bin_path, "--update-kernel="+module.params["kernel_path"]]
    if module.params["state"] == "present":
        grubby_addremove = ""
    elif module.params["state"] == "absent":
        grubby_addremove = "remove-"
    grubby_args += "--"+grubby_addremove+"args=" + " ".join(result["args_added"])

    rc, stdout, stderr = module.run_command([*grubby_args])
    if rc != 0:
        module.fail_json(f"grubby failed", args=grubby_args, rc=rc, stdout=stdout, stderr=stderr)

    result["changed"] = any([result["args_added"], result["args_removed"]])

    module.exit_json(**result)


class FindArgResult(enum.Enum):
    MISSING = enum.auto()
    CHANGED = enum.auto()
    PRESENT = enum.auto()


def find_arg_in(arg, current_args):
    argk, sep, argv = arg.partition("=")
    for current_arg in current_args:
        current_argk, sep, current_argv = current_arg.partition("=")
        if argk == current_argk:
            if argv == current_argv:
                return FindArgResult.PRESENT
            else:
                return FindArgResult.CHANGED
    return FindArgResult.MISSING


if __name__ == '__main__':
    main()
