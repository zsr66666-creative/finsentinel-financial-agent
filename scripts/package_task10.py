"""Source-only Task 10 package; model files stay on the existing ECS release."""
import argparse

from scripts.package_task9 import package

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    package(args.output, args.revision, task='task10')
