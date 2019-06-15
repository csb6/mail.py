import imaplib, sys, email, email.policy, json

config_file = open("config.json")
config = json.loads(config_file.read())
config_file.close()
HOST = config["host"]
USER = config["username"]
PASSWORD = config["password"]

class MailService:
    def __init__(self):
        self.api = imaplib.IMAP4_SSL(HOST)
        try:
            status, data = self.api.login(USER, PASSWORD)
        except imaplib.IMAP4.error:
            print("Error: Cannot login")
            sys.exit(1)

    def error_check(self, status, message):
        if status != "OK":
            print("Error:", message)
            sys.exit(1)

    def get_msgs(self, mailbox, criteria):
        status, data = self.api.select(mailbox)
        self.error_check(status, "couldn't open mailbox")
        status, all_msgs = self.api.search(None, criteria)
        self.error_check(status, "couldn't search")
        msgs = []
        for n in all_msgs[0].split()[:25]:
            msg = {}
            status, msg_data = self.api.fetch(n, '(RFC822)')
            self.error_check(status, "couldn't fetch " + str(n))
            raw_msg = email.message_from_bytes(msg_data[0][1], policy=email.policy.SMTP)
            msg["subject"] = raw_msg.get("Subject")
            msg["from"] = raw_msg.get("From")
            msg["to"] = raw_msg.get("To")
            msg["internalDate"] = raw_msg.get("Date")
            msg["text"] = ""
            if not raw_msg.is_multipart():
                msg["text"] = raw_msg.get_content()
            else:
                for part in raw_msg.get_payload():
                    if part.get_content_type() == "text/plain":
                        msg["text"] = part.get_content()
                        break
            msgs.append(msg)
        return msgs

    def is_synced(self):
        return self.api.recent()[1] == [None]

    def send_msg(self, to, subject, text):
        pass
