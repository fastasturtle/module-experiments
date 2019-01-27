#!/usr/bin/env python3

import argparse
import glob
import os
import sys


class NinjaFile:
    def __init__(self):
        self.rules = []
        self.build_edges = []

    def add_rule(self, name, command):
        self.rules.append("rule {}\n".format(name))
        self.rules.append("  command = {}\n\n".format(command))

    def add_build_edge(self, rule, input, output, deps):
        self.build_edges.append(
            "build {}: {} {} {}\n".format(output, rule, input, "| " + " ".join(deps) if deps else ""))

    def write_to(self, filename):
        with open(filename, 'w+') as f:
            f.writelines(self.rules)
            f.writelines(self.build_edges)


def find_module_names(path):
    res = []
    for file in glob.glob(os.path.join(path, "*.cpp")):
        res.append(os.path.splitext(os.path.basename(file))[0])
    return res


def create_headers(path, compiler):
    module_names = find_module_names(path)
    ninja_file = NinjaFile()
    ninja_file.add_rule("cc", compiler + " -c -O0 $in -o $out")
    for name in module_names:
        ninja_file.add_build_edge("cc", name + ".cpp", name + ".o", None)
    return ninja_file


def scan_deps(path, cpp_names):
    in_deps = {}
    out_deps = {}
    for name in cpp_names:
        if name not in out_deps:
            out_deps[name] = []
        with open(os.path.join(path, name + ".cpp")) as f:
            for line in f.readlines():
                if line.startswith("import"):
                    dep_name = line.replace("import", "").replace(";", "").strip()
                    if dep_name not in in_deps:
                        in_deps[dep_name] = []
                    in_deps[dep_name] += [name]
                    out_deps[name] += [dep_name]
    return in_deps, out_deps


def create_modules(path, compiler, all_artifacts):
    cpp_names = find_module_names(path)
    in_deps, out_deps = scan_deps(path, cpp_names)

    ninja_file = NinjaFile()
    ninja_file.add_rule("cc", compiler + " -fmodules-ts -c -O0 $in -fprebuilt-module-path=. -o $out")
    ninja_file.add_rule("cc-pcm", compiler + " -fmodules-ts -c -O0 $in -fprebuilt-module-path=. "
                                             "-Xclang -fmodules-codegen -Xclang -emit-module-interface "
                                             "-o $out")
    for name in cpp_names:
        deps = [dep + ".pcm" for dep in out_deps[name]]
        has_in_deps = name in in_deps and in_deps[name]
        if all_artifacts or has_in_deps:
            ninja_file.add_build_edge("cc-pcm", name + ".cpp", name + ".pcm", deps)
        if all_artifacts or not has_in_deps:
            ninja_file.add_build_edge("cc", name + ".cpp", name + ".o", deps)

    return ninja_file


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description="""
Generate ninja build files for simple header-based or module-based bunch of files.

Assumptions:
  - All files are named *.cpp or *.h and are placed in the working directory
  - Module names match header names
  - clang with modules-ts support is used
  - Module dependency scanning is performing by looking at `import <name>;` declarations
    """)
    parser.add_argument('--headers', help='Path to header-based sources')
    parser.add_argument('--modules', help='Path to module-based sources')
    parser.add_argument('--compiler', help='Path to the compiler', required=True)
    parser.add_argument('--all-artifacts', help='Build .o for intermediate modules', default=False, action='store_true')
    args = parser.parse_args()

    if args.headers:
        create_headers(args.headers, args.compiler).write_to(os.path.join(args.headers, 'build.ninja'))

    if args.modules:
        create_modules(args.modules, args.compiler, args.all_artifacts).write_to(
            os.path.join(args.modules, 'build.ninja'))


if __name__ == '__main__':
    main()
