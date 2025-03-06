import json
import argparse
import os

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('appmap_file', type=str, help='Appmap file to disable slowlearning on')
    return parser.parse_args()

def build_output_filename(appmap_file):
    file_dir = os.path.dirname(appmap_file)
    file_base = os.path.basename(appmap_file)
    (file_name, _) = os.path.splitext(file_base)
    return os.path.join(file_dir, file_name + "-no-slow-learn.json")

def main():
    args_result = parse_args()

    appmap_file = args_result.appmap_file
    appmap_output = build_output_filename(appmap_file)

    with open(appmap_file, "r") as f:
        appmap_in = json.load(f)
        for app in appmap_in["applications"]:
            app["doNotSlowLearn"] = 1
        with open(appmap_output, "w") as f_out:
            json.dump(appmap_in, f_out)

if __name__ == "__main__":
    main()
