import imaplib, smtplib, sys, email, email.policy, json, re, datetime
from email.mime.text import MIMEText

class MailService:
    def __init__(self):
        config_file = open("config.json")
        self.config = json.loads(config_file.read())
        config_file.close()
 
        self.api = imaplib.IMAP4_SSL(self.config["host"])
        print("Connected to", self.config["host"])
        try:
            self.api.login(self.config["username"], self.config["password"])
        except imaplib.IMAP4.error:
            print("Error: Cannot login to IMAP")
            sys.exit(1)
        print("Logged in to IMAP")

        #To speed up startup, only connect right before 1st message sent
        self.smtp_connected = False

    def error_check(self, status, message):
        if "OK" not in status:
            print("Error:", message)
            sys.exit(1)
        #If UIDs change between sessions, I have no idea how to sync :)
        elif "UIDVALIDITY" in status:
            print("Error: UID values have changed:", status)
            sys.exit(1)

    def get_all_uids(self, mailbox):
        status, data = self.api.select(mailbox)
        self.error_check(status, "couldn't open mailbox")
        status, data = self.api.uid("SEARCH", b'ALL')
        return [int(i) for i in data[0].split()]

    def show_msgs(self, mailbox, criteria, callback):
        print("Getting messages...")
        status, data = self.api.select(mailbox)
        self.error_check(status, "couldn't open mailbox")
        print(" Selected", mailbox)
        status, data = self.api.search(None, criteria)
        self.error_check(status, "couldn't search")
        all_msgs = data[0].split()
        print(" Searched using:", criteria)
        print(" Server data:", all_msgs)
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
            msg["type"] = "text"
            if not raw_msg.is_multipart():
                print("Subject:", msg["subject"], "Content Type:", raw_msg.get_content_type())
                if "html" in raw_msg.get_content_type():
                    msg["type"] = "html"
                msg["text"] = raw_msg.get_content()
            else:
                found = False
                for part in raw_msg.walk():
                    if part.get_content_type() == "text/plain":
                        msg["text"] = part.get_content()
                        found = True
                        break
                if not found:
                    for part in raw_msg.walk():
                        content_type = part.get_content_type()
                        print("Subject:", msg["subject"], "Content Type:", content_type)
                        if "html" in content_type:
                            msg["text"] = part.get_content()
                            msg["type"] = "html"
                            break
            callback(msg)
            if i == (msg_amt-1):
                last_uid = msg["uid"]
        print(" All messages downloaded")
        return last_uid

    def sync_status(self, mailbox, last_uid, client_msg_amt):
        last_uid_str = bytes(str(last_uid), "utf-8")
        status, data = self.api.select(mailbox)
        self.error_check(status, "couldn't open mailbox")
        server_msg_amt = int(data[0])

        status, data = self.api.uid("FETCH", last_uid_str + b':*', "UID")
        new_msgs = [i.split()[0] for i in data
                    if not i.endswith(b' '+last_uid_str+b')')]
        self.error_check(status, "couldn't perform FETCH sync")
        print(data, client_msg_amt, server_msg_amt, new_msgs)
        #Ensure same amt of msgs as last sync, no new msgs added/removed
        is_synced = len(data) == 1 and client_msg_amt == server_msg_amt \
                    and data[-1].endswith(b' '+last_uid_str + b')')
        return is_synced, server_msg_amt, new_msgs

    def send_msg(self, to, subject, text):
        if not self.smtp_connected:
            self.smtp = smtplib.SMTP_SSL("smtp.gmail.com")
            try:
                self.smtp.ehlo_or_helo_if_needed()
                self.smtp.login(self.config["username"], self.config["password"])
                self.smtp_connected = True
            except smtplib.SMTPException as e:
                print("Error:", e)
                sys.exit(1)
            print("Logged in to SMTP")

        msg = MIMEText(text)
        msg["to"], msg["from"], msg["subject"] = to, self.config["username"], subject
        try:
            self.smtp.sendmail(self.config["username"], to, msg.as_string())
            return True
        except smtplib.SMTPException as e:
            print("Error Sending:", e)
            return False
