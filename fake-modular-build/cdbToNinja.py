#!/usr/bin/env python3
import argparse
import json
import shlex
import os
from typing import *

from util import make_absolute


def find_output(args: List[str]) -> str:
    if args:
        for a1, a2 in zip(args[:-1], args[1:]):
            if a1 == '-o':
                return a2
    raise RuntimeError("Can\'t find output in {0}".format(str(args)))


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
    def __init__(self, measuring_compilers_path: Optional[str]):
        self.compilers: Dict[str, str] = {}  # dict of (exec name: var name)
        self.rules: Dict[str, Tuple[str, str]] = {}  # dict of (common_args: (rule_name, rule_text))
        self.edges: List[str] = []
        self.measuring_compilers_path = measuring_compilers_path
        self.input_to_output: Dict[str, str] = {}

    def add_cdb_command(self, command: str, input_file: str, wd: str):
        assert os.path.isabs(wd), 'Only absolute working dirs are supported!'
        args = [shlex.quote(s) for s in shlex.split(command)]
        compiler_var_name = self.add_or_create_compiler(args[0])
        args[0] = '${}'.format(compiler_var_name)
        rel_output = find_output(args)
        output_file = make_absolute(rel_output, wd)
        self.input_to_output[input_file] = output_file
        time_file = rel_output + '.time.json' if self.measuring_compilers_path is not None else None
        input_file = make_absolute(input_file, wd)
        common_args = remove_input_and_output(args, input_file, wd)
        self.add_build_edge(common_args, input_file, output_file, time_file, wd)

    def add_build_edge(self, common_args: str, input_file: str, output_file: str, time_file: Optional[str],
                       working_dir: str):
        rule_name = self.find_or_add_rule(common_args, working_dir)
        self.edges.append(f"build {output_file}{time_file}: {rule_name} {input_file}\n" +
                          f"   obj_file={output_file}\n" +
                          f"   time_trace_file={time_file}\n")

    def find_or_add_rule(self, common_args: str, working_dir: str) -> str:
        key = common_args + working_dir

        existing_rule = self.rules.get(key)
        if existing_rule is not None:
            return existing_rule[0]

        rule_name = 'cc{}'.format(len(self.rules))
        rule_text = f"rule {rule_name}\n" + \
                    f"   command = cd {working_dir} && {common_args} --time-trace $time_trace_file -o $obj_file $in"

        self.rules[key] = (rule_name, rule_text)
        return rule_name

    def get_text(self):
        compilers = self.get_target_compilers()
        return \
            "\n".join(["{} = {}".format(name, exe) for exe, name in compilers.items()]) + \
            "\n\n" + \
            "\n".join(rule_text for rule_name, rule_text in self.rules.values()) + \
            "\n\n" + \
            "\n".join(self.edges) + \
            "\n"

    def add_or_create_compiler(self, compiler):
        if compiler in self.compilers:
            return self.compilers[compiler]
        var_name = "compiler{}".format(len(self.compilers))
        self.compilers[compiler] = var_name
        return var_name

    def get_target_compilers(self) -> Dict[str, str]:
        if self.measuring_compilers_path is None:
            return self.compilers

        c_injected = False
        cpp_injected = False
        result = {}
        for executable, var_name in self.compilers.items():
            looks_like_cpp = '++' in executable
            if looks_like_cpp and cpp_injected or not looks_like_cpp and c_injected:
                raise RuntimeError("Can't inject compilers in {}".format(self.compilers))
            result[os.path.join(self.measuring_compilers_path, 'clang++' if looks_like_cpp else 'clang')] = var_name
        return result

    def get_metadata(self) -> List[Tuple[str, str]]:
        return [(input_path, output_path) for input_path, output_path in self.input_to_output.items()]


def cdb_to_ninja(cdb: Iterable[Mapping[str, str]], measuring_compiler_path: str) -> Tuple[str, List[Tuple[str, str]]]:
    builder = CDBToNinjaBuilder(measuring_compiler_path)
    for entry in cdb:
        builder.add_cdb_command(entry['command'], entry['file'], entry['directory'])

    return builder.get_text(), builder.get_metadata()


def main():
    parser = argparse.ArgumentParser(description='Prepare normal or measuring ninja build script out of CDB')

    parser.add_argument('--cdb-path', help='path to CDB', required=True)
    parser.add_argument('--output-path', help='path to ninja build script output', required=True)
    parser.add_argument('--metadata-path', help='path to store metadata (i.e. .cpp/.o mappings)')
    parser.add_argument('--measuring-compiler-path',
                        help='path to measuring compilers (clang/clang++), omit to use original compiler')
    args = parser.parse_args()

    cdb = json.load(open(args.cdb_path))
    ninja, metadata = cdb_to_ninja(cdb, args.measuring_compiler_path)
    open(args.output_path, 'w').write(ninja)
    if args.metadata_path:
        open(args.metadata_path, 'w').write('\n'.join('"{}" "{}"'.format(ip, op) for ip, op in metadata))


if __name__ == '__main__':
    main()
