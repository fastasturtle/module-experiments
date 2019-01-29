import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

from cdbToNinja import cdb_to_ninja
from createFakeBuild import measurements_to_ninja
from dependenciesForest import collect_results


def measuring_dir(output_path):
    return os.path.join(output_path, 'measuring')


def fake_dir(output_path):
    return os.path.join(output_path, 'fake')


def bmi_dir(output_path):
    return os.path.join(fake_dir(output_path), 'BMI')


def ninja_script_path(build_dir):
    return os.path.join(build_dir, 'build.ninja')


def containing_dir(path):
    assert os.path.isfile(path)
    return os.path.split(path)[0]


def report(*args):
    print(datetime.datetime.now().strftime('%H:%M:%S>'), *args)


def create_dir(path):
    report('Creating', path)
    os.makedirs(path)


def prepare_output_dirs(output_path):
    report('Removing', output_path)
    if os.path.isfile(output_path):
        os.remove(output_path)
    elif os.path.isdir(output_path):
        shutil.rmtree(output_path)

    create_dir(measuring_dir(output_path))
    create_dir(fake_dir(output_path))
    create_dir(bmi_dir(output_path))


def create_measuring_ninja_script(cdb_path, output_path, measuring_compiler_path):
    path = measuring_dir(output_path)
    script_path = ninja_script_path(path)
    report('Creating measuring ninja script in {} for {}'.format(script_path, cdb_path))
    with open(cdb_path) as f:
        cdb_json = json.load(f)
    ninja_text, obj_mapping = cdb_to_ninja(cdb_json, measuring_compiler_path)
    with open(script_path, 'w') as f:
        f.write(ninja_text)

    # this file is not used for now, just for manual inspection
    obj_mapping_path = os.path.join(output_path, 'obj_mapping.json')
    report('Dumping discovered object files mapping to', obj_mapping_path)
    with open(obj_mapping_path, 'w') as f:
        json.dump(obj_mapping, f)

    return script_path, obj_mapping


def report_ninja_time(ninja_script_path, build_name):
    ninja_dir = containing_dir(ninja_script_path)

    clean_command = ['ninja', '-t', 'clean']
    report('Running "{}" for {} build in {}'.format(' '.join(clean_command), build_name, ninja_dir))
    subprocess.check_call(clean_command, cwd=ninja_dir, stdout=subprocess.DEVNULL)

    build_command = ['ninja']
    report('Timing "{}" for {} build in {}'.format(' '.join(build_command), build_name, ninja_dir))
    start_time = time.time()
    subprocess.check_call(build_command, cwd=ninja_dir, stdout=subprocess.DEVNULL)
    elapsed_time = time.time() - start_time

    report('{} build took {:.2f}s'.format(build_name, elapsed_time))
    return elapsed_time


def collect_measuring_results(obj_files_mapping, output_path):
    report('Processing time traces')
    list_of_time_json_files = [obj_file + '.time.json' for _, obj_file in obj_files_mapping]
    results = collect_results(list_of_time_json_files)

    # this file is not used for now, just for manual inspection
    results_paths = os.path.join(output_path, 'results.json')
    report('Dumping processed traces to', results_paths)
    with open(results_paths, 'w') as f:
        f.write(results.to_json())

    return results


def create_fake_ninja_build(measuring_results, output_path):
    fd = fake_dir(output_path)
    script_path = ninja_script_path(fd)
    report('Creating fake ninja script in', script_path)
    script_text = measurements_to_ninja(measuring_results, fd)
    with open(script_path, 'w') as f:
        f.write(script_text)

    return script_path


def main(cdb_path, output_path, measuring_compiler_path):
    prepare_output_dirs(output_path)
    measuring_ninja_script_path, obj_files_mapping = create_measuring_ninja_script(cdb_path, output_path,
                                                                                   measuring_compiler_path)
    normal_time = report_ninja_time(measuring_ninja_script_path, 'measuring')
    measuring_results = collect_measuring_results(obj_files_mapping, output_path)
    fake_build_ninja_script_path = create_fake_ninja_build(measuring_results, output_path)
    modular_time = report_ninja_time(fake_build_ninja_script_path, 'fake')

    print('########################')
    print('normal:  {:.2f}s'.format(normal_time))
    print('modular: {:.2f}s'.format(modular_time))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simulate modular build by measuring header processing times')

    parser.add_argument('--cdb-path', help='path to CDB', required=True)
    parser.add_argument('--output-path', help='path to an directory where various outputs would be stored',
                        required=True)
    parser.add_argument('--force', help='Erase output directory', default=False, action='store_true')
    parser.add_argument('--measuring-compiler-path', help='path to measuring compilers (clang/clang++)', required=True)
    args = parser.parse_args()

    if not args.force and (not os.path.isdir(args.output_path) or os.listdir(args.output_path)):
        print('output directory not empty, pass --force to remove anyway', file=sys.stderr)
        exit(1)

    sys.exit(main(os.path.abspath(args.cdb_path), os.path.abspath(args.output_path),
                  os.path.abspath(args.measuring_compiler_path)))
