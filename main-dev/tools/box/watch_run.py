import sqlite3,json,os,sys
c=sqlite3.connect(os.path.expanduser("~/council/box/db/council.db"))
rid=sys.argv[1] if len(sys.argv)>1 else c.execute("select run_id from events where type='run.created' order by seq desc limit 1").fetchone()[0]
names={}
for t,p in c.execute("select type,payload from events where run_id=? order by seq",(rid,)):
    d=json.loads(p)
    if t=="seat.assigned": names[d["seat_no"]]=d["model_id"]
    elif t=="run.state_changed": print(f"-- state: {d['to_state']}")
    elif t=="model.failed": print(f"!! model failed {d.get('model_id')}: {str(d.get('error'))[:90]}")
    elif t=="round.started": print(f"\n===== ROUND {d['round']} =====")
    elif t=="msg.ended":
        txt=" ".join((d.get("text") or "").split())
        print(f"[{names.get(d['seat_no'],d['seat_no'])}] " + (f"FAILED: {d.get('error')}" if d.get("error") else txt[:330]))
    elif t=="msg.card":
        k=d["card"]; print(f"    card: \"{k.get('note')}\" | to {k.get('to')} | backs {k.get('backs')} | stance: {str(k.get('stance'))[:70]} | conf {k.get('confidence')}")
    elif t=="table.tally": print("  TALLY:", [(g["statement"][:50], g["seat_ids"]) for g in d["groups"]], f"agree {d['agree']}/{d['seats']} need {d['needed']} reached {d['reached']}")
    elif t=="chair.started": print(f"-- deciding vote by seat {d.get('seat_no')} ({d.get('model_id')})")
    elif t=="decision.final": print("\nFINAL:", d["decision"]["outcome"], "|", d["decision"]["final_text"][:400])
