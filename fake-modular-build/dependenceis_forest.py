import json
import os
import pprint
import sys
from typing import *


class Node:
    def __init__(self, name: str):
        self.parent = None
        self.name = name
        self.children: List[Node] = []


class TU:
    def __init__(self, root: Node):
        self.root = root


def fix_path(path):
    if not path: return path
    return os.path.normpath(os.path.realpath(path))


def tu_from_trace(trace, tu_name):
    processing_stack = [tu_name]

    enter_times = {tu_name: 0}
    exit_times = {tu_name: trace['TotalTime']}
    dependencies = {tu_name: set()}

    for event in trace['Events']:
        name = fix_path(event['File'])
        if not name:
            continue

        node_type = event['Type']
        timestamp = event['TimestampMS']
        cur_name = processing_stack[-1]

        if node_type == 'inc-dir':
            continue  # ignore this for now
        elif node_type == 'enter':
            if name in dependencies:
                pass  # todo: do something
            else:
                dependencies[name] = set()

            enter_times[name] = timestamp
            dependencies[cur_name].add(name)
            processing_stack.append(name)

        elif node_type == 'exit':
            if cur_name != name:
                raise RuntimeError(
                    'Stack mismatch! Enter: {}, exit: {}, tu: {}'.format(cur_name, name, tu_name))
            exit_times[name] = timestamp
            processing_stack.pop()
        elif node_type == 'skip':
            if name not in enter_times:
                raise RuntimeError('Skipping unknown header {} in tu {}'.format(name, tu_name))
            elif name not in exit_times:
                print('Recursive include of {} in tu {}, ignoring'.format(name, tu_name))
            else:
                dependencies[cur_name].add(name)

    print('dependencies:')
    pprint.pprint(dependencies)
    print('enter_times:')
    pprint.pprint(enter_times)
    print('exit_times:')
    pprint.pprint(exit_times)


def process_trace(trace_path):
    trace = json.load(open(trace_path))
    tu_name = fix_path(trace_path.replace('.o.time.json', ''))
    tu_from_trace(trace, tu_name)


def main():
    trace_path: str = sys.argv[1]
    process_trace(trace_path)


if __name__ == '__main__':
    main()
