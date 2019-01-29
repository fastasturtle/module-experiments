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
    def __init__(self, dependencies, enter_times, exit_times, total_time_in_children, multi_entry_names):
        self.dependencies = dependencies
        self.enter_times = enter_times
        self.exit_times = exit_times
        self.total_time_in_children = total_time_in_children
        self.multi_entry_names = multi_entry_names
        self.all_nodes = dict()

    def build_all_nodes(self):
        for name in self.enter_times.keys():
            if name not in self.multi_entry_names:
                self.build_node(name)
        return self.all_nodes

    def build_node(self, node_name):
        assert node_name not in self.multi_entry_names

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


def find_multi_entry_names(events, root_dir):
    processed = set()
    result = set()
    for event in events:
        name = fix_path(event['File'], root_dir)
        if not name:
            continue
        if event['Type'] == 'enter':
            if name in processed:
                result.add(name)
            else:
                processed.add(name)
    return result


def cleanup_events(events, root_dir):
    events = events[1:]  # first is TU itself - we don't have matching "exit" for it
    events = [e for e in events if e['Type'] in ('enter', 'exit', 'skip')]  # for now we don't need other events
    idxs_to_skip = set()
    processing_stack = []
    for idx, event in enumerate(events):
        type = event['Type']
        file = fix_path(event['File'], root_dir)
        if not file:
            idxs_to_skip.add(idx)
        elif type == 'enter' and file in processing_stack:
            next_type = events[idx + 1]['Type']
            next_file = fix_path(events[idx + 1]['File'], root_dir)
            if next_type == 'exit' and next_file == file:
                idxs_to_skip.add(idx)
                idxs_to_skip.add(idx + 1)
            else:
                raise RuntimeError('Weird self-include for', file)

        if type == 'enter':
            processing_stack.append(file)
        elif type == 'exit':
            assert processing_stack[-1] == file
            processing_stack.pop()
    return [e for idx, e in enumerate(events) if idx not in idxs_to_skip]


def tu_from_trace(trace, tu_name, root_dir):
    processing_stack = [tu_name]

    enter_times = {tu_name: 0}
    exit_times = {tu_name: trace['TotalTime']}
    total_time_in_children = {tu_name: 0}
    dependencies = {tu_name: set()}
    events = cleanup_events(trace['Events'], root_dir)
    multi_entry_names = find_multi_entry_names(events, root_dir)
    multi_entry_level = 0
    is_in_multi_entry_mode = False

    for event in events:
        name = fix_path(event['File'], root_dir)
        if not name:
            continue

        node_type = event['Type']
        timestamp = event['TimestampMS']
        cur_name = processing_stack[-1]

        if node_type == 'enter' and name in multi_entry_names:
            is_in_multi_entry_mode = True

        if is_in_multi_entry_mode:
            if node_type == 'enter':
                multi_entry_level += 1
                if name not in dependencies:
                    multi_entry_names.add(name)
            elif node_type == 'exit':
                multi_entry_level -= 1

            if multi_entry_level == 0:
                is_in_multi_entry_mode = False

        if node_type == 'inc-dir':
            continue  # ignore this for now
        elif node_type == 'enter':
            dependencies[name] = set()
            enter_times[name] = timestamp
            total_time_in_children[name] = 0

            # for multi-entry headers, record this time as parent's self-time
            # we still want to record dependencies for nested headers in multi-entry mode,
            # if they appear later normally (and are skipped)
            if name not in multi_entry_names:
                dependencies[cur_name].add(name)
            processing_stack.append(name)

        elif node_type == 'exit':
            if cur_name != name:
                raise RuntimeError(
                    'Stack mismatch! Enter: {}, exit: {}, tu: {}'.format(cur_name, name, tu_name))
            exit_times[name] = timestamp
            processing_stack.pop()
            if name not in multi_entry_names:
                total_time_in_children[processing_stack[-1]] += exit_times[name] - enter_times[name]
        elif node_type == 'skip':
            if name not in enter_times:
                raise RuntimeError('Skipping unknown header {} in tu {}'.format(name, tu_name))
            elif name not in exit_times:
                print('Recursive include of {} in tu {}, ignoring'.format(name, tu_name))
            else:
                if name not in multi_entry_names:
                    dependencies[cur_name].add(name)

    builder = NodeBuilder(dependencies, enter_times, exit_times, total_time_in_children, multi_entry_names)
    all_nodes = builder.build_all_nodes()
    tu = all_nodes[tu_name]
    assert tu.total_time == exit_times[tu_name]
    actual = tu.total_time
    computed = sum(c.self_time for c in all_nodes.values())
    assert actual == computed
    return tu, all_nodes, multi_entry_names


def process_trace(trace_path, root_dir):
    trace = json.load(open(trace_path))
    tu_name = fix_path(trace['Events'][0]['File'], root_dir)
    return tu_from_trace(trace, tu_name, root_dir)


def median_build_times(tu_times: Mapping[str, List[int]]) -> Mapping[str, int]:
    return {k: int(statistics.median(v)) for k, v in tu_times.items()}


def collect_results(json_list):
    all_bad_files = set()
    tu_times = {}
    immediate_deps = {}
    object_files = {}
    root_dir = sys.argv[1]
    for tp in json_list:
        print('Processing', tp)
        tu, all_nodes, bad_files = process_trace(tp, root_dir)
        all_bad_files.update(bad_files)
        for n in all_nodes.values():
            if n.name not in tu_times:
                tu_times[n.name] = []
            tu_times[n.name].append(n.self_time)
            immediate_deps[n.name] = set(c.name for c in n.children)
        object_files[tu.name] = tp.replace('.o.time.json', '.o')
    return MeasuringResults(all_bad_files, median_build_times(tu_times), immediate_deps, object_files)


if __name__ == '__main__':
    results = collect_results(glob.iglob(sys.argv[1] + '/**/*.o.time.json', recursive=True))
    open('results.json', 'w').write(results.to_json())
