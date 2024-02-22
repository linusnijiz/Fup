import json, requests, ast, random

with open("jsons/env.json", "r") as f:
    envData = json.load(f)

with open("jsons/wunderTuten.json", "r") as f:
    wunderData = json.load(f)

with open("jsons/preisliste.json", "r") as f:
    preisliste = json.load(f)


def execute_service(items):
    newItemList = []
    for item in items:
        if item["Produkt"] == "Guthaben":
            menge = float(item["Menge"])
            with open("jsons/users.json", "r") as f:
                users = json.load(f)
            
            for user in users:
                if user["Email"] == item["Recepient"]:
                    if not "Guthaben" in user:
                        user["Guthaben"] = menge
                    else:
                        user["Guthaben"] += menge
                    
                    item["Status"] = "completed"
            
            with open("jsons/users.json", "w") as f:
                json.dump(users, f, indent=2)
            newItemList.append(item)
        else:       
            print(item)            
            if item["Produkt"] == "Instagram Wundertuete" or item["Produkt"] == "TikTok Wundertuete":
                ProfileRecepient = item["Recepient"]
                WunderRecepient = item["WunderRecepient"]
                del item["Recepient"]
                del item["WunderRecepient"]
                item["Status"] = "Completed"
                newItemList.append(item)
                for index, produkt in enumerate(wunderData[item["Produkt"]][item["Menge"]]):
                    mengenList = wunderData[item["Produkt"]][item["Menge"]][produkt]
                    if index == 0:
                        recepient = ProfileRecepient
                    else:
                        recepient = WunderRecepient
                    Id = ""
                    for id in preisliste:
                        if preisliste[id] == produkt:
                            Id = str(preisliste[id][Id])
                    newItem = {
                        "Produkt" : f'{produkt} - aus Wundertuete {item["Menge"]}',
                        "Menge" : random.randrange(mengenList[0], mengenList[1]),
                        "Recepient" : recepient,
                        "Id" : Id
                    }
                    execute_standard_item(newItem)
                    newItemList.append(newItem)
            elif item["Id"] in [8265, 6273, 5978, 5988]:
                commentList = ast.literal_eval(item["Menge"])
                comments = ""
                print(commentList)
                for i in range(len(commentList)):
                    comments += commentList[i] + "\n"
                print(comments)
                payload = {
                    "key" : "69f6dc20f0b14410e300a3e6a50ad48b",
                    "action" : "add",
                    "service" : str(item["Id"]),
                    "link" : item["Recepient"],
                    "comments" : comments
                }

                response = requests.post(envData["FasterSMMUrl"], data=payload).json()
                print(response)

                if "order" in response:
                    item["FasterId"] = response["order"]
                    item["Status"] = "In progress"
                else:
                    item["Status"] = response["error"]
                newItemList.append(item)
            else:
                execute_standard_item(item)
                newItemList.append(item)

    return newItemList

def execute_standard_item(item):
    payload = {
        "key" : envData["FasterSMMapiKey"],
        "action" : "add",
        "service" : str(item["Id"]),
        "link" : item["Recepient"],
        "quantity" : str(item["Menge"])
    }

    response = requests.post(envData["FasterSMMUrl"], data=payload).json()
    print(response)

    if "order" in response:
        item["FasterId"] = response["order"]
        item["Status"] = "In progress"
    else:
        item["Status"] = response["error"]

def check_status(item):
    if item["Produkt"] == "Guthaben":
        return
    if not "FasterId" in item:
        return
    payload = {
        "key" : envData["FasterSMMapiKey"],
        "action" : "status",
        "order" : item["FasterId"]
    }

    response = requests.post(envData["FasterSMMUrl"], data=payload).json()
    print(response)

    if "status" in response:
        item["Status"] = response["status"]
    else:
        item["Status"] = response["error"]


