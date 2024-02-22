import json

with open("jsons/wunderTüten.json", "r") as f:
    dic = json.load(f)
    

with open("jsons/preisliste.json", "w") as f:
    json.dump(dic, f, indent=2)
