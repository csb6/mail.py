import imaplib, smtplib, sys, email, email.policy, json, re, datetime
from email.mime.text import MIMEText

config_file = open("config.json")
config = json.loads(config_file.read())
config_file.close()
HOST = config["host"]
USER = config["username"]
PASSWORD = config["password"]

class MailService:
    def __init__(self):
        self.api = imaplib.IMAP4_SSL(HOST)
        print("Connected to", HOST)
        try:
            self.api.login(USER, PASSWORD)
        except imaplib.IMAP4.error:
            print("Error: Cannot login to IMAP")
            sys.exit(1)
        print("Logged in to IMAP")

        self.smtp = smtplib.SMTP_SSL("smtp.gmail.com")
        try:
            self.smtp.ehlo_or_helo_if_needed()
            self.smtp.login(USER, PASSWORD)
        except smtplib.SMTPException as e:
            print("Error:", e)
            sys.exit(1)
        print("Logged in to SMTP")

    def error_check(self, status, message):
        if "OK" not in status:
            print("Error:", message)
            sys.exit(1)
        #If UIDs change between sessions, I have no idea how to sync :)
        elif "UIDVALIDITY" in status:
            print("Error: UID values have changed:", status)
            sys.exit(1)

    def show_msgs(self, mailbox, criteria, callback):
        print("Getting messages...")
        status, data = self.api.select(mailbox)
        self.error_check(status, "couldn't open mailbox")
        print(" Selected", mailbox)
        status, data = self.api.search(None, criteria)
        self.error_check(status, "couldn't search")
        all_msgs = data[0].split()
        print(" Searched using:", criteria)
        last_uid = None
        msg_amt = len(all_msgs)
        for i, n in enumerate(all_msgs):
            msg = {}
            status, msg_data = self.api.fetch(n, '(UID RFC822)')
            self.error_check(status, "couldn't fetch " + str(n))
            num, uid_label, uid, tail = msg_data[0][0].split(b' ', 3)
            msg["uid"] = int(uid)
            raw_msg = email.message_from_bytes(msg_data[0][1], policy=email.policy.SMTP)
            msg["subject"] = raw_msg.get("Subject")
            msg["from"] = raw_msg.get("From")
            msg["to"] = raw_msg.get("To")
            date_str = raw_msg.get("Date")
            if re.findall(r'^[A-Za-z]{3}, [0-9]{2} [A-Za-z]{3} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} (\+|-)[0-9]{4}$', date_str):
                date = datetime.datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
                msg["internalDate"] = date.ctime()
            else:
                print("Time string failed to match format:", date_str)
                msg["internalDate"] = date_str
            msg["text"] = ""
            if not raw_msg.is_multipart():
                msg["text"] = raw_msg.get_content()
            else:
                for part in raw_msg.get_payload():
                    if part.get_content_type() == "text/plain":
                        msg["text"] = part.get_content()
                        break
            callback(msg)
            if i == (msg_amt-1):
                last_uid = msg["uid"]
        print(" All messages downloaded")
        return last_uid, msg_amt

    def is_synced(self, mailbox, last_uid, client_msg_amt):
        status, server_msg_amt = self.api.select(mailbox)
        self.error_check(status, "couldn't open mailbox")
        status, data = self.api.uid("FETCH", bytes(str(last_uid), "utf-8") + b':*', "UID")
        self.error_check(status, "couldn't perform FETCH sync")
        print(data, client_msg_amt, server_msg_amt[0])
        #Ensure same amt of msgs as last sync, no new msgs added/removed
        return len(data) == 1 and client_msg_amt == int(server_msg_amt[0]) \
               and data[0].endswith(bytes(str(last_uid), "utf-8") + b')')

    def send_msg(self, to, subject, text):
        msg = MIMEText(text)
        msg["to"], msg["from"], msg["subject"] = to, USER, subject
        try:
            self.smtp.sendmail(USER, to, msg.as_string())
            return True
        except smtplib.SMTPException as e:
            print("Error Sending:", e)
            return False
