import argparse
import json
from .service import WorkMemory

def build_parser():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",default=".runtime")
    sub=parser.add_subparsers(dest="cmd",required=True)
    for name in ("init","health","pending","alerts","supervisor","status"):
        sub.add_parser(name)
    search=sub.add_parser("search")
    search.add_argument("query")
    return parser

def dispatch(wm,args):
    handlers={
        "init": lambda: {"ok":True,"root":args.root},
        "health": wm.health,
        "pending": wm.pending,
        "alerts": wm.list_alerts,
        "supervisor": wm.supervisor_tick,
        "status": wm.status_snapshot,
        "search": lambda: wm.search(args.query),
    }
    return handlers[args.cmd]()

def main():
    args=build_parser().parse_args()
    result=dispatch(WorkMemory(args.root),args)
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__":
    main()
