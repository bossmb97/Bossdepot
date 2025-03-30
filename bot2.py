import telebot
import sqlite3
import threading
import os
import time

# 🛠️ Configuration sécurisée
TOKEN = "7037622732:AAGeUbwnxIPze-8IqXsApo6_KTfLttOhAes"  # Stocke ton token en variable d'environnement
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", 7555089736))  # ID admin

bot = telebot.TeleBot(TOKEN)
lock = threading.Lock()

# 📌 Fonction pour gérer la connexion SQLite (évite les accès concurrents)
def get_db_connection():
    return sqlite3.connect("balance.db", check_same_thread=False)

# 📌 Création des tables si elles n'existent pas
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            bonus REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            status TEXT DEFAULT 'pending'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL,
            date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO account (id, balance) VALUES (1, 0.0)")
    conn.commit()

# 🔍 Fonction pour récupérer le solde
def get_balance():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM account WHERE id = 1")
        return cursor.fetchone()[0]
        
        
# 🔍 Fonction pour récupérer le bonus
def get_bonus():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bonus FROM account WHERE id = 1")
        return cursor.fetchone()[0]

# 🔄 Fonction pour mettre à jour le solde après une transaction
def update_balance(amount):
    with lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM account WHERE id = 1")
            current_balance = cursor.fetchone()[0]
            new_balance = current_balance - amount
            if new_balance < 0:
                return False
            cursor.execute("UPDATE account SET balance = ? WHERE id = 1", (new_balance,))
            conn.commit()
            return True

# 🔄 Fonction pour ajouter du solde
def add_balance(amount):
    with lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE account SET balance = balance + ? WHERE id = 1", (amount,))
            cursor.execute("INSERT INTO history (amount) VALUES (?)", (amount,))
            conn.commit()

# 📌 Commande pour afficher le solde
@bot.message_handler(commands=['solde'])
def check_balance(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut voir le solde.")
        return
    balance = get_balance()
    bot.reply_to(message, f"💰 Solde actuel : {balance:.2f} DA")



# 📌 Commande pour afficher le bonus
@bot.message_handler(commands=['bonus'])
def check_bonus(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut voir le bonus.")
        return
    bonus = get_bonus()
    bot.reply_to(message, f"💰 Bonus actuel : {bonus:.2f} DA")
    
# 📌 Commande pour envoyer une demande de paiement
@bot.message_handler(commands=['demande'])
def request_payment(message):
    try:
        parts = message.text.split()
        user_id = message.chat.id
        amount = float(parts[1])
        if amount <= 0:
            raise ValueError

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM transactions WHERE status = 'pending'")
            existing_request = cursor.fetchone()
            
            if existing_request:
                bot.reply_to(message, "❌ Une demande en attente.")
                return
            
            cursor.execute("INSERT INTO transactions (user_id, amount, status) VALUES (?, ?, 'pending')", (user_id, amount))
            conn.commit()

        bot.send_message(ADMIN_ID, f"📢 Nouvelle demande de paiement\n👤 ID : {user_id}\n💰 Montant : {amount:.2f} DA\n 🌟 Bonus : {0.01*amount:.2f} DA\n"
                                   f"👉 Réponds avec /valider pour confirmer.\n"
                                   f"👉 Réponds avec /annuler pour annuler.")
        bot.reply_to(message, "✅ Demande envoyée à l'admin. Attends la confirmation ou annule avec /annuler.")
    
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Utilisation incorrecte. Exemple : /demande 200")

# 📌 Commande pour valider une transaction  

@bot.message_handler(commands=['valider'])
def confirm_payment(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut valider les transactions.")
        return

    try:
        with lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Récupérer la première transaction en attente
                cursor.execute("SELECT id, user_id, amount FROM transactions WHERE status = 'pending' ")
                transaction = cursor.fetchone()

                if not transaction:
                    bot.reply_to(message, "❌ Aucune transaction en attente.")
                    return

                transaction_id, user_id, amount = transaction
                bot.reply_to(message, f"📌 Transaction trouvée : ID {transaction_id}, Utilisateur {user_id}, Montant {amount:.2f} DA")
# Vérifier le solde de l'admin
                admin_balance = get_balance()
                admin_bonus = get_bonus()
                
                if admin_balance < amount:
                    bot.reply_to(message, "❌ Solde insuffisant !")
                    return  # Ajout du return pour éviter l'erreur d'indentation
                else    : 
                     # Si le solde est suffisant, mise à jour du statut et du solde
                     newbalance =admin_balance-amount
                     newbonus = admin_bonus +0.01*amount
                     
                     
                     cursor.execute("UPDATE account SET balance = ? WHERE id = 1", (newbalance,))
                     conn.commit()
                     
                     
                     cursor.execute("UPDATE account SET bonus = ? WHERE id = 1", (newbonus,))
                     conn.commit()
                    
                                                 
                cursor.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (transaction_id,))
                conn.commit()
                
                bot.send_message(user_id, f"✅ Paiement de {amount:.2f} DA validé par l'admin.")
                bot.reply_to(message, f"✅ Transaction validée. Nouveau solde : {newbalance:.2f} DA \n Nouveau bonus :{newbonus:.2f} DA")

    except Exception as e:
        bot.reply_to(message, f"❌ Erreur : {str(e)}")
        print("Erreur :", e)
  
# 📌 Commande pour annuler une demande en attente
@bot.message_handler(commands=['annuler'])
def cancel_request(message):
    user_id = message.chat.id
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM transactions WHERE  status = 'pending' " )
        transaction = cursor.fetchone()
        
        if not transaction:
            bot.reply_to(message, "❌ Aucune demande en attente à annuler.")
            return
        
        cursor.execute("UPDATE transactions SET status = 'canceled' WHERE id = ?", (transaction[0],))
        conn.commit()
    
    bot.reply_to(message, "✅ Votre demande de paiement a été annulée.")
    bot.send_message(ADMIN_ID, f"⚠️ Demande de paiement annulée\n👤 ID : {user_id}")
# pour ajouter du solde (admin uniquement)
@bot.message_handler(commands=['addsolde'])
def add_solde(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut ajouter du solde.")
        return

    try:
        parts = message.text.split()
        amount = float(parts[1])
        if amount <= 0:
            raise ValueError

        add_balance(amount)
        bot.reply_to(message, f"✅ {amount:.2f} DA ajoutés au solde.\n💰 Nouveau solde : {get_balance():.2f} DA")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Utilisation incorrecte. Exemple : /addsolde 500")

# 📌 Commande pour ajouter du solde (admin uniquement)
@bot.message_handler(commands=['addsolde'])
def add_solde(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut ajouter du solde.")
        return

    try:
        parts = message.text.split()
        amount = float(parts[1])
        if amount <= 0:
            raise ValueError

        add_balance(amount)
        bot.reply_to(message, f"✅ {amount:.2f} DA ajoutés au solde.\n💰 Nouveau solde : {get_balance():.2f} DA")

    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Utilisation incorrecte. Exemple : /addsolde 500")

# 📌 Commande pour afficher l'historique des 10 derniers ajouts de solde
@bot.message_handler(commands=['historique'])
def view_history(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut voir l'historique.")
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, date FROM history ORDER BY id DESC LIMIT 10")
        history = cursor.fetchall()
    if not history:
        bot.reply_to(message, "📜 Aucun ajout de solde enregistré.")
    else:
        history_text = "📜 *Historique des 10 derniers ajouts de solde :*\n"
        for entry in history:
            history_text += f"💰 {entry[0]:.2f} DA - 🕒 {entry[1]}\n"

        bot.reply_to(message, history_text, parse_mode="Markdown")

# 📌 Commande pour afficher l'historique des 10 derniers transactions
@bot.message_handler(commands=['transactions'])
def view_history(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut voir l'historique.")
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, amount from TRANSACTIONS ORDER BY id DESC LIMIT 10")
        history = cursor.fetchall()
    if not history:
        bot.reply_to(message, "📜 Aucune transaction enregistrée.")
    else:
        history_text = "📜 *Historique des 10 dernières transactions :*\n"
        for entry in history:
            history_text += f"💰 {entry[0]:}  - 🕒 {entry[1]} DA\n"

        bot.reply_to(message, history_text, parse_mode="Markdown")
        
        # 📌 Commande /help pour afficher toutes les commandes disponibles
@bot.message_handler(commands=['help'])
def help_command(message):
    if message.chat.id == ADMIN_ID:
        help_text = """📌 *Commandes Admin :*
🔹 /solde - Afficher le solde total
🔹 /bonus - Afficher le bonus total
🔹 /valider <ID> <montant> - Valider une transaction
🔹 /addsolde <montant> - Ajouter du solde
🔹 /historique - Voir l’historique des ajouts de solde
🔹 /transactions - Voir l’historique des transactions effectuées

🔹 /reset - Réinitialiser le solde
🔹 /help - Voir cette aide"""
    else:
        help_text = """📌 *Commandes Utilisateur :*
🔹 /demande <montant> - Envoyer une demande de paiement
🔹 /help - Voir cette aide"""

    bot.reply_to(message, help_text, parse_mode="Markdown")

# 📌 Commande pour réinitialiser le solde
@bot.message_handler(commands=['reset'])
def reset_balance(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Seul l'admin peut réinitialiser le solde.")
        return

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE account SET balance = 0.0 WHERE id = 1")
        conn.commit()
    bot.reply_to(message, "🔄 Solde réinitialisé à 0 DA.")

# 📌 Réponse pour les commandes inconnues
@bot.message_handler(func=lambda message: True)
def unknown_command(message):
    bot.reply_to(message, "❌ Commande inconnue. Utilise /solde, /demande, /valider, /addsolde, /historique ou /reset.")

# 🚀 Lancement sécurisé du bot avec gestion des erreurs
print("Bot en cours d'exécution...")

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Erreur : {e}")
        time.sleep(5)  # Attente avant de redémarrer le bot