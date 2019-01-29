import os
import sys

import MeasuringResults

from typing import *

MODULE_RULE = 'fake_module'
OBJFILE_RULE = 'fake_objfile'
MIN_TIME_TO_SPAWN_COMPILER = 0.015

BUILD_EDGE_TEMPLATE = """
build {output}: {rule_name} {input} {dependencies}
    wait_time = {wait_time:.6f}
    cat_times = {cat_times}
""".strip()

RULES = """
rule {module_rule}
    command = sleep $wait_time && truncate -s 0 $out && seq 1 $cat_times | xargs -Inone cat $in >> $out

rule {objfile_rule}
    command = sleep $wait_time && touch $out
""".format(module_rule=MODULE_RULE, objfile_rule=OBJFILE_RULE).strip()


class NinjaBuilder:
    def __init__(self):
        self.edges: List[str] = []

    def add_fake_command(self, rule_name: str, wait_time_us: int, source_input: str, module_inputs: List[str],
                         output: str):
        if module_inputs:
            implicit_deps_part = ' | ' + ' '.join(module_inputs)
        else:
            implicit_deps_part = ''
        self.edges.append(BUILD_EDGE_TEMPLATE.format(
            rule_name=rule_name,
            output=output,
            input=source_input, dependencies=implicit_deps_part,
            wait_time=(wait_time_us / 1000000.) + MIN_TIME_TO_SPAWN_COMPILER,
            cat_times=5))

    def build(self):
        return RULES + '\n\n' + '\n\n'.join(self.edges) + '\n'


def get_bmi_path(input_name: str, path: str) -> str:
    return os.path.join(path, 'BMI', input_name.replace('/', '_') + '.bmi')


def measurements_to_ninja(m: MeasuringResults.MeasuringResults, result_path: str) -> str:
    builder = NinjaBuilder()

    for input_name, self_time in m.build_times.items():
        object_file = m.object_files.get(input_name)
        deps = [get_bmi_path(dep, result_path) for dep in m.immediate_deps[input_name]]
        if object_file:  # source
            builder.add_fake_command(OBJFILE_RULE, self_time, input_name, deps, object_file)
        else:  # module
            builder.add_fake_command(MODULE_RULE, self_time, input_name, deps, get_bmi_path(input_name, result_path))

    return builder.build()


if __name__ == '__main__':
    measuring_results = MeasuringResults.from_json(open(sys.argv[1]).read())
    results_path = sys.argv[2]
    ninja_script = measurements_to_ninja(measuring_results, results_path)
    ninja_build_path = os.path.join(results_path, 'build.ninja')
    open(ninja_build_path, 'w').write(ninja_script)
