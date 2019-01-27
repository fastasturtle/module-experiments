#!/usr/bin/env python3

import sys
import json
import shlex
import os
from typing import *


def find_output(args: List[str]) -> str:
    if args:
        for a1, a2 in zip(args[:-1], args[1:]):
            if a1 == '-o':
                return a2
    raise RuntimeError("Can\'t find output in {0}".format(str(args)))


def make_absolute(path: str, wd: str) -> str:
    return os.path.normpath(os.path.join(wd, path))


def remove_input_and_output(args: List[str], input_file: str, wd: str) -> str:
    skip_next = False
    result = []
    for arg in args:
        if arg == '-o':
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if make_absolute(arg, wd) == input_file:
            continue
        result.append(arg)
    return ' '.join(result)


class CDBToNinjaBuilder:
    def __init__(self):
        self.rules: Dict[str, Tuple[str, str]] = {}  # dict of (common_args: (rule_name, rule_text))
        self.edges: List[str] = []

    def add_cdb_command(self, command: str, input_file: str, wd: str):
        assert os.path.isabs(wd), 'Only absolute working dirs are supported!'
        args = shlex.split(command)
        output_file = make_absolute(find_output(args), wd)
        input_file = make_absolute(input_file, wd)
        common_args = remove_input_and_output(args, input_file, wd)
        self.add_build_edge(common_args, input_file, output_file, wd)

    def add_build_edge(self, common_args: str, input_file: str, output_file: str, working_dir: str):
        rule_name = self.find_or_add_rule(common_args, working_dir)
        self.edges.append("build {}: {} {}".format(output_file, rule_name, input_file))

    def find_or_add_rule(self, common_args: str, working_dir: str) -> str:
        key = common_args + working_dir

        existing_rule = self.rules.get(key)
        if existing_rule is not None:
            return existing_rule[0]

        rule_name = 'cc{}'.format(len(self.rules))
        rule_text = "rule {}\n".format(rule_name) + \
                    "   command = cd {} && {} -o $out $in".format(working_dir, common_args)
        self.rules[key] = (rule_name, rule_text)
        return rule_name

    def get_text(self):
        return \
            "\n".join(rule_text for rule_name, rule_text in self.rules.values()) + \
            "\n\n" + \
            "\n".join(self.edges) + \
            "\n"


def cdb_to_ninja(cdb) -> str:
    builder = CDBToNinjaBuilder()
    for entry in cdb:
        builder.add_cdb_command(entry['command'], entry['file'], entry['directory'])
    return builder.get_text()


def main():
    if len(sys.argv) != 3:
        print("Usage: cdb-to-ninja <path-to-cdb> <path-to-output>")
        sys.exit(1)

    cdb = json.load(open(sys.argv[1]))
    ninja = cdb_to_ninja(cdb)
    open(sys.argv[2], 'w').write(ninja)


if __name__ == '__main__':
    main()
