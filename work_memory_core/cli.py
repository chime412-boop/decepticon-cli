import argparse,json
from .service import WorkMemory
def main():
 p=argparse.ArgumentParser();p.add_argument("--root",default=".runtime");s=p.add_subparsers(dest="cmd",required=True)
 for c in ("init","health","pending"): s.add_parser(c)
 x=s.add_parser("search");x.add_argument("query");a=p.parse_args();w=WorkMemory(a.root)
 if a.cmd=="init": out={"ok":True,"root":a.root}
 elif a.cmd=="health": out=w.health()
 elif a.cmd=="pending": out=w.pending()
 else: out=w.search(a.query)
 print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=="__main__": main()
