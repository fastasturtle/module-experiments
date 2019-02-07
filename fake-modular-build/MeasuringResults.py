import json
from typing import *


class MeasuringResults:
    def __init__(self, build_times: Mapping[str, int], immediate_deps: Mapping[str, Set[str]],
                 object_files: Mapping[str, str]):
        self.build_times = build_times
        self.immediate_deps = immediate_deps
        self.object_files = object_files

    def to_json(self) -> str:
        return json.dumps({
            'build_times': {p: d for p, d in self.build_times.items()},
            'immediate_deps': {p: sorted(list(d)) for p, d in self.immediate_deps.items()},
            'object_files': self.object_files
        }, indent=2)


def from_json(json_text: str) -> MeasuringResults:
    data = json.loads(json_text)
    build_times = {cpp: t for cpp, t in data['build_times'].items()}
    immediate_deps = {path: deps for path, deps in data['immediate_deps'].items()}
    object_files = {cpp: obj for cpp, obj in data['object_files'].items()}
    return MeasuringResults(build_times, immediate_deps, object_files)
