"""Package committed Task11 sources; reuse existing ECS model and official PDFs."""
import argparse
from scripts.package_task9 import package
if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--revision',default='HEAD')
    args=parser.parse_args()
    package(args.output,args.revision,task='task11')
