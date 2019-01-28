import json
import os
import sys


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


def fix_path(path):
    if not path: return path
    return os.path.normpath(os.path.realpath(path))


def find_multi_entry_names(events):
    processed = set()
    result = set()
    for event in events:
        name = fix_path(event['File'])
        if not name:
            continue
        if event['Type'] == 'enter':
            if name in processed:
                result.add(name)
            else:
                processed.add(name)
    return result


def tu_from_trace(trace, tu_name):
    processing_stack = [tu_name]

    enter_times = {tu_name: 0}
    exit_times = {tu_name: trace['TotalTime']}
    total_time_in_children = {tu_name: 0}
    dependencies = {tu_name: set()}
    multi_entry_names = find_multi_entry_names(trace['Events'])
    multi_entry_level = 0
    is_in_multi_entry_mode = False

    for event in trace['Events'][1:]:  # first is TU itself - we don't have matching "exit" for it
        name = fix_path(event['File'])
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
                dependencies[cur_name].add(name)

    builder = NodeBuilder(dependencies, enter_times, exit_times, total_time_in_children, multi_entry_names)
    all_nodes = builder.build_all_nodes()
    tu = all_nodes[tu_name]
    # print(tu.dump_tree())
    assert tu.total_time == exit_times[tu_name]
    for k, v in all_nodes.items():
        print(k, v.self_time)
    assert tu.total_time == sum(c.self_time for c in all_nodes.values())
    return tu


def process_trace(trace_path):
    trace = json.load(open(trace_path))
    tu_name = fix_path(trace['Events'][0]['File'])
    tu = tu_from_trace(trace, tu_name)
    print(tu.dump_tree())


def main():
    trace_path: str = sys.argv[1]
    process_trace(trace_path)


if __name__ == '__main__':
    main()
