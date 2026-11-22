import json
a = json.load(open("dry/seen.json"))
m = a.get("_meta", {})
out = {"meta_keys": sorted(m.keys()), "shop_at": m.get("shop_at"), "health": m.get("health"),
       "fc_fresh2": m.get("fc_fresh2"), "sources": {}}
for k, v in a.items():
    if isinstance(v, dict) and v.get("source"):
        out["sources"][v["source"]] = out["sources"].get(v["source"], 0) + 1
json.dump(out, open("hw_dryrun_report.json", "w"), indent=1)
