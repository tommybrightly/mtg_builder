import csv
with open("commanders.csv", 'r') as f, open("commanders.txt","w") as out:
    r = csv.DictReader(f)
    seen=set()
    for row in r:
        name=row.get("name") or row.get("Name")
        if not name: 
            continue
        if name in seen: 
            continue
        seen.add(name)
        out.write(name+"\n")
