from flask import Flask, request, jsonify, redirect, app
from threading import Thread
from datetime import datetime, timedelta
import paypalrestsdk, json, random, bcrypt, base64, jwt, datetime, pytz
from paypalrestsdk import Payment
from flask_cors import CORS
from send_mail import send_email
from services import execute_service, check_status
from dc import startBot

format = "%d.%m.%Y, %H:%M"
germanyTimezone = pytz.timezone('Europe/Berlin')

with open("jsons/env.json", "r") as f:
    envData = json.load(f)

paypalrestsdk.configure({
    "mode": envData["ppStatus"],
    "client_id": envData["ppClientId"],
    "client_secret": envData["ppClientSecret"]
})

app = Flask('FollowUpBackend')
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

app.config['SECRET_KEY'] = envData["sk"]

@app.route('/current_user', methods=["POST"])
def get_current_user():
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if result['valid']:
        # Aktuelle User holen
        with open("jsons/users.json", "r") as f:
            users = json.load(f)

        for user in users:
            if user["Email"] == result["email"]:
                if "Bestellungen" in user:
                    for Bestellung in user["Bestellungen"]:
                        for item in Bestellung["items"]:
                            if not item["Status"] == "Completed":
                                item = check_status(item)
                with open("jsons/users.json", "w") as f:
                    json.dump(users, f, indent=2)
                del user["Passwort"]
                return jsonify(user), 200
    else:
        return jsonify({'error': result['error']})


@app.route('/', methods=["GET", "POST"])
def home():
    return "hii"

def check_jwt_validity(token):
    if not token:
        return jsonify({'error': 'token not found'})
    try:
        # Use secret key to verify the token
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        
        # Assuming the payload contains an 'email' field
        email = payload.get('email')
        
        return {'valid': True, 'email': email}
    except jwt.ExpiredSignatureError:
        return {'valid': False, 'error': 'token has expired'}
    except jwt.InvalidTokenError:
        return {'valid': False, 'error': 'token invalid'}
# Account Management Endpoints
def hash_password(password):
    # Generate a salt and hash the password
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password

def check_password(entered_password, stored_hashed_password):
    # Decode base64-encoded hashed password and salt
    decoded_hashed_password = base64.b64decode(stored_hashed_password.encode('utf-8'))

    # Check if the entered password matches the stored hashed password
    return bcrypt.checkpw(entered_password.encode('utf-8'), decoded_hashed_password)

def generate_token(email):
    payload = {
        'exp': datetime.datetime.utcnow() + timedelta(days=1),  # Token expiration time
        'email': email  # Subject (in this case, email)
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
    return token

# Called after first Attempt to register
@app.route('/verifyEmail', methods=["POST"])
def verifyEmail():
    # Extract Email and Password
    if not "newEmail" in request.json:
        return {"error" : "email missing"}
    if not "newPassword" in request.json:
        return {"error" : "password missing"}
    
    newEmail = request.json.get("newEmail")
    newPassword = request.json.get("newPassword")
    
    # Aktuelle User holen
    with open("jsons/users.json", "r") as f:
     users = json.load(f)

    # Checken ob user email schon registriert und verifiziert
    for user in users:
        if user["Email"] == newEmail and not "verificationCode" in user:
            return {"error" : "email not available"}
        
    # Checken ob user email schon vorhanden
    for user in users:
       if user["Email"] == newEmail:
          users.remove(user)
          with open("jsons/users.json", "w") as f:
            json.dump(users, f, indent=2)

    hashedPassword = hash_password(newPassword)
    verificationCode = random.randrange(100000, 1000000)
    user = {
        "Email": newEmail,
        "verificationCode": str(verificationCode)
    }
     # Encode the password to a base64-encoded string
    user['Passwort'] = base64.b64encode(hashedPassword).decode('utf-8')

    # neuen User ergänzen
    with open("jsons/users.json", "r") as f:
     users = json.load(f)
    users.append(user)
    with open("jsons/users.json", "w") as f:
       json.dump(users, f, indent=2)
    
    mailHeader = "Dein Verifizierungs Code"
    mailContent = f"Du hast versucht dich mit dieser Mail Adresse bei uns zu registrieren. Gib dafür diesen Code ein:<br><br> {verificationCode}<br><br>Du warst das nicht? Dann kannst du diese Nachricht ignorieren."
    subject = f"Verifizierungs Code {verificationCode}"
    send_email(subject, newEmail, mailHeader, mailContent)
    
    return {"success" : "mail sent"}


def authenticate_user(email, password):
    with open("jsons/users.json", "r") as f:
      users = json.load(f)

    for user in users: # suche in usern nach user mit entsprechender mail adresse
        if user["Email"] == email and check_password(password, user["Passwort"]): 
            if "verificationCode" in user:
               return {"error" : "email not verified"}
            else:
                return user
            
    return {"error" : "wrong combi"}

@app.route('/login', methods=["POST"])
def login():
    email = request.json.get('email')
    password = request.json.get('password')

    # Authenticate user (check credentials against database)
    user_data = authenticate_user(email, password)

    if "error" in user_data:
       return user_data
    
    jwtToken = generate_token(email)
    return jsonify({'jwt': jwtToken, "user" : user_data}), 200


# When User enters Validation Code from Email
@app.route('/register', methods=["POST"])
def register():
    email = request.json.get('newEmail')
    code = request.json.get('code')

    with open("jsons/users.json", "r") as f:
      users = json.load(f)

    for user in users:
       if user["Email"] == email and user["verificationCode"] == code:
          del user["verificationCode"]
          with open("jsons/users.json", "w") as f:
            json.dump(users, f, indent=2)
          return {"success" : "erfolgreich registriert"}
       
    return {"error" : "wrong code"}

# Called for resetting Password in case forgot or user just wants to change it
@app.route('/resetPassword', methods=["POST"])
def resetPassword():
    # Extract Email and Password
    if not "email" in request.json:
        return {"error" : "email missing"}
    
    email = request.json.get("email")
    currentUser = None
    # Aktuelle User holen
    with open("jsons/users.json", "r") as f:
     users = json.load(f)

    
    # Checken ob user email schon registriert und verifiziert
    for user in users:
        if user["Email"] == email:
            if "resetCode" in user:
                datelist = user["resetCode"]["date"]
                mailSentDate = datetime.datetime(year=datelist[4], month=datelist[3], day=datelist[2], hour=datelist[1], minute=datelist[0])
                if mailSentDate + datetime.timedelta(minutes=15) > datetime.datetime.now():
                    return {"error" : "mail already sent"}
            currentUser = user
        
    if currentUser == None:
        return {"error" : "user not found"}
    
    resetCode = random.randrange(100000, 1000000)
    now = datetime.datetime.now()
    user["resetCode"] = {"code" : str(resetCode), "date" : [now.minute, now.hour, now.day, now.month, now.year]}

    with open("jsons/users.json", "w") as f:
       json.dump(users, f, indent=2)
    
    mailHeader = "Passwort zurücksetzen"
    mailContent = f"Du hast einen Code angefordert, um dein Passwort zurückzusetzen. Gib dafür diesen Code ein:<br><br> {resetCode}<br><br>Du warst das nicht? Dann kannst du diese Nachricht ignorieren."
    subject = f"Passwort Reset {resetCode}"
    send_email(subject, email, mailHeader, mailContent)
    
    return {"success" : "mail sent"}

  
# Called for checking if the code is correct
@app.route('/checkResetCode', methods=["POST"])
def checkResetCode():
    # Extract Email and Password
    if not "email" in request.json:
        return {"error" : "email missing"}
    if not "code" in request.json:
        return {"error" : "code missing"}
    
    email = request.json.get("email")
    code = request.json.get("code")
    currentUser = None
    # Aktuelle User holen
    with open("jsons/users.json", "r") as f:
     users = json.load(f)

    
    # Checken ob code vorhanden und richtig
    for user in users:
        if user["Email"] == email:
            if "resetCode" in user:
                if user["resetCode"]["code"] == code:
                    return {"success" : "code correct"}
                else:
                    return {"error" : "incorrect code"}
    
    return {"error" : "no code found"}


# set new Password with given resetCode
@app.route('/setNewPassword', methods=["POST"])
def setNewPassword():
    # Extract Email and Password
    if not "email" in request.json:
        return {"error" : "email missing"}
    if not "newPassword" in request.json:
        return {"error" : "password missing"}
    if not "code" in request.json:
        return {"error" : "code missing"}
    
    email = request.json.get("email")
    code = request.json.get("code")
    newPassword = request.json.get("newPassword")
    currentUser = None
    # Aktuelle User holen
    with open("jsons/users.json", "r") as f:
     users = json.load(f)

    
    # Checken ob code vorhanden und richtig
    for user in users:
        if user["Email"] == email:
            if "resetCode" in user:
                if user["resetCode"]["code"] == code:
                    # Neues Passwort setzen
                    hashedPassword = hash_password(newPassword)
                    # Encode the password to a base64-encoded string
                    user['Passwort'] = base64.b64encode(hashedPassword).decode('utf-8')

                    # Bestätigung schicken
                    mailHeader = "Dein Passwort wurde zurückgesetzt"
                    mailContent = f"Hiermit wird die Änderung deines Passworts bestätigt<br><br>Du warst das nicht? Melde dich beim Support."
                    subject = f"Passwort wurde zurückgesetzt"
                    send_email(subject, email, mailHeader, mailContent)
                    del user["resetCode"]
                    with open("jsons/users.json", "w") as f:
                        json.dump(users, f, indent=2)
                    return {"success" : "code correct"}
                else:
                    return {"error" : "incorrect code"}
    
    return {"error" : "no code found"}

# Account functions Ende!


# Wendet RabattCode an
@app.route('/rabattCode', methods=["POST"])
def rabattCode():
    if not "code" in request.json:
        return {"error" : "no code"}
    code = request.json.get("code")

    if not "zwischenSumme" in request.json:
        return {"error" : "no sum"}
    zwischenSumme = request.json.get("zwischenSumme")

    with open("jsons/codes.json", "r") as f:
        codes = json.load(f)
        
    if not code in codes:
        return {"error": "invalid code"}
    elif zwischenSumme < codes[code][1]:
        print(zwischenSumme, codes[code][1])
        return {"error": "sum to small"}
    else:
        return {code: codes[code]}


# Sonder Endpoints
    
# lade Details für instaComments
@app.route('/Instacomments', methods=["GET"])
def Instacomments():
    with open("jsons/preisliste.json", "r") as f:
        preisliste = json.load(f)

    for id in preisliste:
        if preisliste[id]["Produkt"] == "Instagram Wunschkommentare":
            preisliste[id]["id"] = id
            return jsonify(preisliste[id])  # Use jsonify to ensure proper JSON response

    return jsonify({"error": "not found"})

# lade Details für tiktokComments
@app.route('/Tiktokcomments', methods=["GET"])
def Tiktokcomments():
    with open("jsons/preisliste.json", "r") as f:
        preisliste = json.load(f)

    for id in preisliste:
        if preisliste[id]["Produkt"] == "TikTok Wunschkommentare":
            preisliste[id]["id"] = id
            return jsonify(preisliste[id])  # Use jsonify to ensure proper JSON response

    return jsonify({"error": "not found"})

# lade Details für instaBlueComments
@app.route('/Instabluecommentlike', methods=["GET"])
def Instabluecommentlike():
    with open("jsons/preisliste.json", "r") as f:
        preisliste = json.load(f)

    for id in preisliste:
        if preisliste[id]["Produkt"] == "Instagram Kommentar+Like (Blauer Haken Acc.)":
            preisliste[id]["id"] = id
            return jsonify(preisliste[id])  # Use jsonify to ensure proper JSON response

    return jsonify({"error": "not found"})


# Lade Produkte
@app.route('/getAllProducts', methods=["GET"])
def getAllProducts():
    with open("jsons/preisliste.json", "r") as f:
        preisliste = json.load(f)

    return preisliste

# zum Warenkorb hinzufügen
@app.route('/addToWarenkorb', methods=["PUT"])
def addToWarenkorb():
    # Check if user is logged in
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if not result['valid']:
        return jsonify({'error': result['error']})
    else:
        email = result["email"]

    if not "ProduktId" in request.json:
        return jsonify({'error': 'produkt id missing'})
    produktId = request.json.get("ProduktId")

    if not "Recepient" in request.json:
        return {"error": "recepient missing"}
    recepient = request.json.get("Recepient")

    with open("jsons/users.json", "r") as f:
        users = json.load(f)

    for user in users:
        if user["Email"] == email:
            if not "Warenkorb" in user:
                user["Warenkorb"] = []
            newItem = {"id" : str(produktId), "recepient" : recepient}
            if "comments" in request.json:
                # For Comment Products, check if its already in Warenkorb
                for item in user["Warenkorb"]:
                    if "Comments" in item:
                        return {"error" : "product already in"}
                newItem["Comments"] = request.json.get("comments")
            if "WunderRecepient" in request.json:
                newItem["WunderRecepient"] = request.json.get("WunderRecepient")
            user["Warenkorb"].append(newItem)
            with open("jsons/users.json", "w") as f:
                json.dump(users, f, indent=2)
            return {"success" : "added the item"}
        
    return {"error" : "an error occured"}

# Aus Warenkorb entfernen
@app.route('/removeFromWarenkorb', methods=["DELETE"])
def removeFromWarenkorb():
    # Check if user is logged in
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if not result['valid']:
        return jsonify({'error': result['error']})
    else:
        email = result["email"]

    if not "ProduktId" in request.json:
        return jsonify({'error': 'produkt id missing'})
    produktId = request.json.get("ProduktId")


    with open("jsons/users.json", "r") as f:
        users = json.load(f)

    for user in users:
        if user["Email"] == email:
            for ware in user["Warenkorb"]:
                if str(ware["id"]) == str(produktId):
                    user["Warenkorb"].remove(ware)
                    with open("jsons/users.json", "w") as f:
                        json.dump(users, f, indent=2)
                    return {"success": "removed the item"}
        
    return {"error" : "an error occured"}


# Warenkorb fetchen
@app.route('/getWarenkorb', methods=["POST"])
def getWarenkorb():
     # Check if user is logged in
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if not result['valid']:
        return jsonify({'error': result['error']})
    else:
        email = result["email"]

    with open("jsons/users.json", "r") as f:
        users = json.load(f)

    for user in users:
        if user["Email"] == email:
            if not "Warenkorb" in user:
                return {"error" : "warenkorb leer"}
            if not user["Warenkorb"]:
                return {"error" : "warenkorb leer"}
            warenkorb = user["Warenkorb"]
            break

    
    with open("jsons/preisliste.json", "r") as f:
        preisListe = json.load(f)

    orders = []
    total = 0
    commentAlreadyExists = False
    for ware in warenkorb:
        if not str(ware["id"]) in preisListe or commentAlreadyExists and "comments" in ware:
            user["Warenkorb"].remove(ware)
            with open("jsons/users.json", "w") as f:
                json.dump(users, f, indent=2)
            continue
        order = preisListe[str(ware["id"])]
        if "WunderRecepient" in ware:
            order["WunderRecepient"] = ware["WunderRecepient"]
        if "Comments" in ware:
            commentAlreadyExists = True
            order["Preis"] = round(len(ware["Comments"]) * float(order["Preis"]), 2)
            total += float(order["Preis"])
            order["Comments"] = ware["Comments"]
        else:
            total += float(order["Preis"])
        if "Id" in order:
            del order["Id"]
        order["Recepient"] = ware["recepient"]
        order["ProduktId"] = str(ware["id"])

        orders.append(order)
        print(orders)
    return {"orders" : orders, "total" : round(total, 2)}


# Details zu lokalem Warenkorb fetchen
@app.route('/getLocalWarenkorb', methods=["POST"])
def getLocalWarenkorb():
    if not "Warenkorb" in request.json:
        return {"error" : "warenkorb missing"}
    warenkorb = request.json.get("Warenkorb").copy()

    with open("jsons/preisliste.json", "r") as f:
        preisListe = json.load(f)

    orders = []
    total = 0
    commentAlreadyExists = False
    for ware in request.json.get("Warenkorb"):
        if not str(ware["id"]) in preisListe or commentAlreadyExists and "comments" in ware:
            warenkorb.remove(ware)
            continue
        order = preisListe[str(ware["id"])]
        if "Id" in order:
            del order["Id"]
        order["Recepient"] = ware["recepient"]
        if "WunderRecepient" in ware:
            order["WunderRecepient"] = ware["WunderRecepient"]
        order["ProduktId"] = str(ware["id"])
        if "comments" in ware:
            commentAlreadyExists = True
            order["Preis"] = round(len(ware["comments"]) * float(order["Preis"]), 2)
            total += float(order["Preis"])
            order["Comments"] = ware["comments"]
        else:
            total += float(order["Preis"])
        orders.append(order)
    return jsonify({"orders" : orders, "total" : round(total, 2), "warenkorb" : warenkorb})


# Guthaben Checkout
@app.route('/guthabenCheckout', methods=["POST"])
def guthabenCheckout():
     # Check if user is logged in
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if not result['valid']:
        return jsonify({'error': result['error']})
    else:
        email = result["email"]

       # Check if Warenkorb not empty
    with open("jsons/users.json", "r") as f:
        users = json.load(f)
    for user in users:
        if user["Email"] == email:
            current_user = user
            if not "Warenkorb" in user:
                return {"error" : "warenkorb leer"}
            if not user["Warenkorb"]:
                return {"error" : "warenkorb leer"}
            warenkorb = user["Warenkorb"]
            break

    with open("jsons/preisliste.json", "r") as f:
        preisListe = json.load(f)

    # Check if Code is given
    usedCode = "keinen Code benutzt"
    rabatt = None
    if "code" in request.json:
        enteredCode = request.json.get("code")
        with open("jsons/codes.json", "r") as f:
            codes = json.load(f)
            for code in codes:
                if  code == enteredCode:
                    usedCode = code
                    rabatt = codes[code]

    items = []
    total = 0
    for ware in warenkorb:
        if not ware["id"] in preisListe:
            warenkorb.remove(ware)
        order = preisListe[ware["id"]]
        if "Comments" in ware:
            menge = str(ware["Comments"])
        else:
            menge = order["Menge"]
        newItem = {
            "Produkt" : order["Produkt"],
            "Menge" : menge,
            "Preis" : order["Preis"],
            "Recepient" : ware["recepient"],
        }
        if "Id" in order:
            newItem["Id"] = order["Id"]
        if "WunderRecepient" in order:
            newItem["WunderRecepient"] = order["WunderRecepient"]
        
        items.append(newItem)
        total += float(order["Preis"])

    with open("jsons/users.json", "w") as f:
        json.dump(users, f, indent=2)

    if not items:
        return {"error" : "warenkorb leer"}

    if rabatt:
        if total >= rabatt[1]:
            total *= round((100 - rabatt[0]) / 100, 2)

    if not "Guthaben" in current_user:
        return {"error" : "kein guthaben"}
    if current_user["Guthaben"] < total:
        return {"error" : "guthaben reicht nicht"}

    current_user["Guthaben"] -= total
    current_user["Guthaben"] = round(current_user["Guthaben"], 2)
    current_user["Warenkorb"] = []

    with open("jsons/users.json", "w") as f:
        json.dump(users, f, indent=2)
    
    # Services ausführen
    items = execute_service(items)
    

    order = {
        "PaymentId" : "Guthaben Zahlung",
        "Buyer" : email,
        "items" : items,
        "Total" : total,
        "Code" : usedCode,
        "Datum" : datetime.datetime.now(germanyTimezone).strftime(format)
    }

    # Order wird in alle Orders und die Orders des Users eingetragen
    log_order(order)

    # User wird auf OrderCompleted weitergeleitet
    return {"success" : "orderCompleted"}



# Paypal Payment Endpoints 

@app.route('/createOrder', methods=["POST"])
def createOrder():
    # Check if user is logged in
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if not result['valid']:
        return jsonify({'error': result['error']})
    else:
        email = result["email"]

    orderIds = None
    commentLists = []
    # Check if productId is given -> direct payment
    if "productId" in request.json:
        productId = request.json.get("productId")
        guthabenKauf = False
        if 99 < int(productId) < 200:
            guthabenKauf = True
        if not "recepient" in request.json and not guthabenKauf:
            return {"error" : "recepient missing"}
        if productId in ["73", "26", "274"] and not "comments" in request.json:
            return {"error" : "comments missing"}
        commentList = []
        if productId in ["73", "26", "274"]:
            commentList = request.json.get("comments")
        commentLists.append(commentList)
        recepients = [request.json.get("recepient")]
        orderIds = [productId]


    with open("jsons/preisliste.json") as f:
        preisListe = json.load(f)

    # Check if Warenkorb not empty for case checkout
    if not orderIds:
        with open("jsons/users.json", "r") as f:
            users = json.load(f)
        for user in users:
            if user["Email"] == email:
                current_user = user
                if not "Warenkorb" in user:
                    return {"error" : "warenkorb leer"}
                if not user["Warenkorb"]:
                    return {"error" : "warenkorb leer"}
                orderIds = []
                recepients = []
                WunderRecepients = []
                for ware in user["Warenkorb"]:
                    if not ware["id"] in preisListe:
                        user["Warenkorb"].remove(ware)
                    commentList = []
                    if "Comments" in ware:
                        commentList = ware["Comments"]
                    commentLists.append(commentList)
                    orderIds.append(ware["id"])
                    recepients.append(ware["recepient"])
                    WunderRecepient = "None"
                    if "WunderRecepient" in ware:
                        WunderRecepient = ware["WunderRecepient"]
                    WunderRecepients.append(WunderRecepient)
                with open("jsons/users.json", "w") as f:
                    json.dump(users, f, indent=2)


    if not orderIds:
        return {"error": "warenkorb leer"}
    
    # Check if Code is given
    rabatt = 0
    usedCode = "keinen Code benutzt"
    if "code" in request.json:
        enteredCode = request.json.get("code")
        with open("jsons/codes.json", "r") as f:
            codes = json.load(f)
            for code in codes:
                if  code == enteredCode:
                    usedCode = code
                    rabatt = codes[code]

    items = []
    total = 0
    for i in range(len(orderIds)):
        orderId = orderIds[i]
        order = preisListe[orderId]
        recepient = recepients[i]
        WunderRecepient = WunderRecepients[i]
        commentList = commentLists[i]
        preis = order["Preis"]
        Id = 0
        if "Id" in order:
            Id = order["Id"]
        if orderId in ["73", "26", "274"]:
            menge = commentList
            preis = round(float(order["Preis"]) * len(commentList), 2)
        else:
            menge = order["Menge"]

        if order["Produkt"] == "Guthaben":
            name = f'{order["Produkt"]}-{menge}-{email}'
        else:
           name = f'{order["Produkt"]}-{menge}-{email}-{recepient}-{usedCode}-{Id}-{WunderRecepient}' 
        items.append(
            {
                "name": name,
                "price": preis,
                "currency": "EUR",
                "quantity": 1
            }   
        )
        total += float(preis)

    if rabatt:
        if total >= rabatt[1]:
            total *= round((100 - rabatt[0]) / 100, 2)

    payment = Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": envData["returnUrl"],
            "cancel_url": envData["homePage"]
        },
        "transactions": [{
            "item_list": {
                "items": items
            },
            "amount": {
                "total": total,
                "currency": "EUR"
            }
        }]
    })

    # Create and execute payment
    if payment.create():
        print("Payment[%s] created successfully" % (payment.id))
        # Redirect the user to given approval url
        for link in payment.links:
            if link.method == "REDIRECT":
                redirect_url = link.href
    else:
        print("Error while creating payment:")
        print(payment.error)   
        return {"error" : "error creating payment"}
    return {"redirect" : redirect_url}


@app.route('/return')
def paypal_returned():
    if not "paymentId" in request.args or not "PayerID" in request.args:
        return {"error" : "no payment found"}
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')

    try:
        payment_to_execute = Payment.find(payment_id)
    except:
        return {"error" : "no valid payment found"}

    # Check if payment is fresh
    with open("jsons/orders.json", "r") as f:
        orders = json.load(f)

    for order in orders:
      if "PaymentId" in order:
        if order["PaymentId"] == payment_id:
            return {"error" :"Payment has already been executed or is in an invalid state."}
        
    if payment_to_execute.state == 'created' or payment_to_execute.state == 'approved':
        execute_payment = payment_to_execute.execute({"payer_id": payer_id})
    else:
        return {"error" :"Payment has already been executed or is in an invalid state."}

    # Extrahiere items aus payment details
    items = []
    for i in range(len(payment_to_execute.transactions[0].item_list.items)):
        item_name = payment_to_execute.transactions[0].item_list.items[i].name
        preis = payment_to_execute.transactions[0].item_list.items[i].price
        product_details = item_name.split("-")
        try:
            produkt = product_details[0]
            menge = product_details[1]
            buyer = product_details[2]
            recepient = buyer
            Id = None
            usedCode = "keinen Code benutzt"
            if len(product_details) > 3:
                recepient = product_details[3]
                usedCode = product_details[4]
                Id = product_details[5]
                WunderRecepient = product_details[6]
        except IndexError:
            return {"error": "no valid payment found"}
        item = {
                "Produkt" : produkt,
                "Menge" : menge,
                "Preis" : preis,
                "Recepient" : recepient,
                "WunderRecepient" : WunderRecepient,
                "Id" : Id
        }
        items.append(item)


    # Service ausführen
    items = execute_service(items)    

    # Order Daten zusammentragen und items rein
    total_price = payment_to_execute.transactions[0].amount.total
    order = {
        "PaymentId" : payment_id,
        "Buyer" : buyer,
        "items" : items,
        "Total" : total_price,
        "Code" : usedCode,
        "Datum" : datetime.datetime.now(germanyTimezone).strftime(format)
    }

    # Order wird in alle Orders und die Orders des Users eingetragen
    log_order(order)

    # User wird auf OrderCompleted weitergeleitet
    return redirect(envData["orderCompleted"])

def log_order(order):
    email = order["Buyer"]
    print(email)
    with open("jsons/orders.json", "r") as f:
        orders = json.load(f)

    order["Bestellnummer"] = len(orders)
    orders.append(order)

    with open("jsons/orders.json", "w") as f:
        json.dump(orders, f, indent=2)

    with open("jsons/users.json", "r") as f:
        users = json.load(f)

    del order["Buyer"]

    for user in users:
        if user["Email"] == email:
            user["Warenkorb"] = []
            if not "Bestellungen" in user:
                user["Bestellungen"] = [order]
            else:
                user["Bestellungen"].append(order)

    mailHeader = "Bestellung erfolgreich"
    mailContent = f"Hier sind deine Bestelldetails. <br><br>Bestellnummer: {len(orders)}<br>Payment ID: {order['PaymentId']}"
    mailContent += f"<br>Summe: {order['Total']}<br>"
    for item in order["items"]:
        preis = ""
        if "Preis" in item:
            preis = f"<br>Preis: {item['Preis']}"
        mailContent += f"<br><br>Produkt: {item['Produkt']}<br>Menge: {item['Menge']}{preis}"
    subject = f"Bestellnummer: {len(orders)}"
    send_email(subject, email, mailHeader, mailContent)

    with open("jsons/users.json", "w") as f:
        json.dump(users, f, indent=2)

def log_guest_order(order):
    email = order["Email"]
    del order["Email"]
    with open("jsons/orders.json", "r") as f:
        orders = json.load(f)

    order["Bestellnummer"] = len(orders)
    orders.append(order)

    mailHeader = "Bestellung erfolgreich"
    mailContent = f"Hier sind deine Bestelldetails. <br><br>Bestellnummer: {len(orders)}<br>Payment ID: {order['PaymentId']}"
    mailContent += f"<br>Summe: {order['Total']}<br>"
    for item in order["items"]:
        preis = ""
        if "Preis" in item:
            preis = f"<br>Preis: {item['Preis']}"
        mailContent += f"<br><br>Produkt: {item['Produkt']}<br>Menge: {item['Menge']}f{preis}"
    subject = f"Bestellnummer: {len(orders)}"
    send_email(subject, email, mailHeader, mailContent)

    with open("jsons/orders.json", "w") as f:
        json.dump(orders, f, indent=2)


@app.route('/createGuestOrder', methods=["POST"])
def createGuestOrder():
    if not "localWarenkorb" in request.json:
        return {"error" : "localWarenkorb missing"}
    if not "email" in request.json:
        return {"error" : "email missing"}

    localWarenkorb = request.json.get("localWarenkorb")
    if not localWarenkorb:
        return {"error" : "localWarenkorb missing"}
    email = request.json.get("email")

    with open("jsons/preisliste.json") as f:
        preisListe = json.load(f)
    
    # Check if Code is given
    rabatt = 0
    usedCode = "keinen Code benutzt"
    if "code" in request.json:
        enteredCode = request.json.get("code")
        with open("jsons/codes.json", "r") as f:
            codes = json.load(f)
            for code in codes:
                if  code == enteredCode:
                    usedCode = code
                    rabatt = codes[code]

    

    with open("jsons/env.json") as f:
        envData = json.load(f)

    orderIdentifier = envData["orderIdentifier"]
    envData["orderIdentifier"] = orderIdentifier + 1

    with open("jsons/env.json", "w") as f:
        json.dump(envData, f, indent=2)

    # Create a PayPal payment
    items = []
    total = 0
    for item in localWarenkorb:
        orderId = item["id"]
        order = preisListe[orderId]
        recepient = item["recepient"]
        preis = order["Preis"]
        Id = 0
        if "Id" in order:
            Id = order["Id"]
        WunderRecepient = "None"
        if "WunderRecepient" in item:
            WunderRecepient = item["WunderRecepient"]
        if orderId in ["73", "26", "274"]:
            menge = item["comments"]
            preis = round(float(order["Preis"]) * len(item["comments"]), 2)
        else:
            menge = order["Menge"]
        name = f'{order["Produkt"]}-{menge}-{orderIdentifier}-{recepient}-{usedCode}-{order["Id"]}-{email}-{WunderRecepient}' 
        items.append(
            {
                "name": name,
                "price": preis,
                "currency": "EUR",
                "quantity": 1
            }   
        )
        total += float(preis)

    if rabatt:
        if total >= rabatt[1]:
            total *= round((100 - rabatt[0]) / 100, 2)

    payment = Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": envData["returnUrl"]+"Guest",
            "cancel_url": envData["homePage"]
        },
        "transactions": [{
            "item_list": {
                "items": items
            },
            "amount": {
                "total": total,
                "currency": "EUR"
            }
        }]
    })

    # Create and execute payment
    if payment.create():
        print("Payment[%s] created successfully" % (payment.id))
        # Redirect the user to given approval url
        for link in payment.links:
            if link.method == "REDIRECT":
                redirect_url = link.href
    else:
        print("Error while creating payment:")
        print(payment.error)   
        return {"error" : "error creating payment"}
    return {"redirect" : redirect_url, "orderIdentifier" : orderIdentifier}


@app.route('/returnGuest')
def paypal_returned_guest():
    if not "paymentId" in request.args or not "PayerID" in request.args:
        return {"error" : "no payment found"}
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')

    try:
        payment_to_execute = Payment.find(payment_id)
    except:
        return {"error" : "no valid payment found"}

    # Check if payment is fresh
    with open("jsons/orders.json", "r") as f:
        orders = json.load(f)

    for order in orders:
      if "PaymentId" in order:
        if order["PaymentId"] == payment_id:
            return {"error" :"Payment has already been executed or is in an invalid state."}
        
    if payment_to_execute.state == 'created' or payment_to_execute.state == 'approved':
        execute_payment = payment_to_execute.execute({"payer_id": payer_id})
    else:
        return {"error" :"Payment has already been executed or is in an invalid state."}

    # Extrahiere items aus payment details
    items = []
    for i in range(len(payment_to_execute.transactions[0].item_list.items)):
        item_name = payment_to_execute.transactions[0].item_list.items[i].name
        preis = payment_to_execute.transactions[0].item_list.items[i].price
        product_details = item_name.split("-")
        try:
            produkt = product_details[0]
            menge = product_details[1]
            buyer = product_details[2]
            recepient = product_details[3]
            usedCode = product_details[4]
            Id = product_details[5]
            email = product_details[6]
            WunderRecepient = product_details[7]
        except IndexError:
            return {"error": "no valid payment found"}
        item = {
                "Produkt" : produkt,
                "Menge" : menge,
                "Preis" : preis,
                "Recepient" : recepient,
                "WunderRecepient" : WunderRecepient,
                "Id" : Id
        }
        items.append(item)

        
    # Service ausführen
    items = execute_service(items)
    
    # order Daten zusammentragen
    total_price = payment_to_execute.transactions[0].amount.total
    order = {
        "PaymentId" : payment_id,
        "Email" : email,
        "BuyId" : buyer,
        "items" : items,
        "Total" : total_price,
        "Code" : usedCode,
        "Datum" : datetime.datetime.now(germanyTimezone).strftime(format)
    }

    # Order wird in alle Orders und die Orders des Users eingetragen
    log_guest_order(order)

    # User wird auf OrderCompleted weitergeleitet
    return redirect(envData["orderCompleted"])

# Für Order Completed
@app.route('/getLatestOrder', methods=["POST"])
def getLatestOrder():
    # Check if user is logged in
    token_data = request.json.get('token')
    result = check_jwt_validity(token_data)

    if not result['valid']:
        return jsonify({'error': result['error']})
    else:
        email = result["email"]

    with open("jsons/users.json", "r") as f:
        users = json.load(f)

    for user in users:
        if email == user["Email"] and "Bestellungen" in user:
            latestOrder = user["Bestellungen"][-1]

            for item in latestOrder["items"]:
                check_status(item)
            return jsonify(latestOrder)
        
    return jsonify({'error': 'no orders found'})


@app.route('/getLatestGuestOrder', methods=["POST"])
def getLatestGuestOrder():
    if not "orderIdentifier" in request.json:
        return {"error" : "orderIdentifier missing"}

    orderIdentifier = request.json.get("orderIdentifier")
    with open("jsons/orders.json", "r") as f:
        orders = json.load(f)

    for order in orders:
        if "BuyId" in order:
            if order["BuyId"] == orderIdentifier:
                return jsonify(order)
        
    return jsonify({'error': 'no orders found'})


# Starting Flask App
def run():
  app.run(host='0.0.0.0', port=8080, ssl_context=('cert.pem', 'key.pem'))

def start():
    t = Thread(target=run)
    t.start()


start()
startBot()
