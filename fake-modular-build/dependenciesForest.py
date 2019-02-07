import glob
import json
import os
import statistics
import sys
from MeasuringResults import MeasuringResults
from typing import *


class Node:
    def __init__(self, name: str, children, self_time, total_time):
        self.parent = None
        self.name = name
        self.children = children
        self.self_time = self_time
        self.total_time = total_time

    def __repr__(self):
        return '{}, self-time: {}, total-time: {}, children count: {}'.format(self.name, self.self_time,
                                                                              self.total_time, len(self.children))

    def dump_tree(self, indent=0):
        return '\n'.join([' ' * indent + str(self)] + [child.dump_tree(indent + 1) for child in self.children])


class NodeBuilder:
    def __init__(self, dependencies, enter_times, exit_times, total_time_in_children):
        self.dependencies = dependencies
        self.enter_times = enter_times
        self.exit_times = exit_times
        self.total_time_in_children = total_time_in_children
        self.all_nodes = dict()

    def build_all_nodes(self):
        for name in self.enter_times.keys():
            self.build_node(name)
        return self.all_nodes

    def build_node(self, node_name):
        if node_name in self.all_nodes:
            return self.all_nodes[node_name]

        children = [self.build_node(dep) for dep in self.dependencies[node_name]]
        total_time = self.exit_times[node_name] - self.enter_times[node_name]
        self_time = total_time - self.total_time_in_children[node_name]
        node = Node(node_name, children, self_time, total_time)
        self.all_nodes[node_name] = node
        return node


def fix_path(path, root_dir):
    if not path:
        return path
    if not os.path.isabs(path):
        path = os.path.join(root_dir, path)
    res = os.path.normpath(os.path.realpath(path))
    return res


def cleanup_events(events, root_dir):
    events = events[1:]  # first is TU itself - we don't have matching "exit" for it
    events = [e for e in events if e['Type'] in ('enter', 'exit', 'skip')]  # for now we don't need other events
    return events


def tu_from_trace(trace, tu_name, root_dir):
    processing_stack = [(tu_name, False)]

    enter_times = {tu_name: 0}
    exit_times = {tu_name: trace['TotalTime']}
    total_time_in_children = {tu_name: 0}
    dependencies = {tu_name: set()}
    events = cleanup_events(trace['Events'], root_dir)

    level = 0
    for event in events:
        name = fix_path(event['File'], root_dir)
        if not name:
            continue

        node_type = event['Type']
        timestamp = event['TimestampMS']
        cur_name = processing_stack[-1][0]
        cur_name_is_multientry = processing_stack[-1][1]

        if node_type == 'enter':
            is_multientry = name in dependencies
            if not is_multientry:
                dependencies[name] = set()
                enter_times[name] = timestamp
                total_time_in_children[name] = 0
                dependencies[cur_name].add(name)

            processing_stack.append((name, is_multientry))
            # print(' ' * level, 'Entering', name, is_multientry)
            level += 1

        elif node_type == 'exit':
            if cur_name != name:
                raise RuntimeError(
                    'Stack mismatch! Enter: {}, exit: {}, tu: {}'.format(cur_name, name, tu_name))

            processing_stack.pop()
            if not cur_name_is_multientry:
                exit_times[name] = timestamp
                if not processing_stack[-1][1]:
                    total_time_in_children[processing_stack[-1][0]] += exit_times[name] - enter_times[name]
            level -= 1
            t = (exit_times[name] - enter_times[name]) if name in exit_times else '???'
            # print(' ' * level, 'Leaving', name, t)

        elif node_type == 'skip':
            if not cur_name_is_multientry:
                if name not in enter_times:
                    raise RuntimeError('Skipping unknown header {} in tu {}'.format(name, tu_name))
                elif name not in exit_times:
                    pass
                    # print('Recursive include of {} in tu {}, ignoring'.format(name, tu_name))
                elif not cur_name_is_multientry:
                    dependencies[cur_name].add(name)

    builder = NodeBuilder(dependencies, enter_times, exit_times, total_time_in_children)
    all_nodes = builder.build_all_nodes()
    tu = all_nodes[tu_name]
    assert tu.total_time == exit_times[tu_name]
    # actual = tu.total_time
    # computed = sum(c.self_time for c in all_nodes.values())
    # print(f'actual={actual}, computed={computed}, diff={computed - actual}')
    return tu, all_nodes


def process_trace(trace_path, root_dir):
    trace = json.load(open(trace_path))
    tu_name = fix_path(trace['Events'][0]['File'], root_dir)
    return tu_from_trace(trace, tu_name, root_dir)


def median_build_times(tu_times: Mapping[str, List[int]]) -> Mapping[str, int]:
    return {k: int(statistics.median(v)) for k, v in tu_times.items()}


def collect_results(json_list):
    tu_times = {}
    immediate_deps = {}
    object_files = {}
    root_dir = sys.argv[1]
    for tp in json_list:
        print('    Processing', tp)
        tu, all_nodes = process_trace(tp, root_dir)
        for n in all_nodes.values():
            if n.name not in tu_times:
                tu_times[n.name] = []
            tu_times[n.name].append(n.self_time)
            immediate_deps[n.name] = set(c.name for c in n.children)
        object_files[tu.name] = tp.replace('.o.time.json', '.o')
    return MeasuringResults(median_build_times(tu_times), immediate_deps, object_files)


if __name__ == '__main__':
    results = collect_results(glob.iglob(sys.argv[1] + '/**/*.o.time.json', recursive=True))
    open('results.json', 'w').write(results.to_json())
